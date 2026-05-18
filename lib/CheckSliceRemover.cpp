#include "DESAN/CheckSliceRemover.h"

#include "llvm/ADT/STLExtras.h"
#include "llvm/ADT/SmallPtrSet.h"
#include "llvm/ADT/SmallVector.h"
#include "llvm/ADT/StringRef.h"
#include "llvm/ADT/iterator_range.h"
#include "llvm/IR/CFG.h"
#include "llvm/IR/Constants.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/InlineAsm.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/IntrinsicInst.h"
#include "llvm/IR/Module.h"
#include "llvm/IR/ValueHandle.h"
#include "llvm/Transforms/Utils/BasicBlockUtils.h"
#include "llvm/Transforms/Utils/Local.h"

#include <algorithm>

using namespace llvm;

namespace desan {

namespace {

bool isNoopIntrinsic(const Instruction *I) {
  if (isa<DbgInfoIntrinsic>(I))
    return true;

  const auto *II = dyn_cast<IntrinsicInst>(I);
  if (!II)
    return false;

  switch (II->getIntrinsicID()) {
  case Intrinsic::lifetime_start:
  case Intrinsic::lifetime_end:
  case Intrinsic::invariant_start:
  case Intrinsic::invariant_end:
    return true;
  default:
    return false;
  }
}

bool isReportBlockTerminator(const Instruction *TI) {
  if (isa<UnreachableInst>(TI))
    return true;

  const auto *BI = dyn_cast<BranchInst>(TI);
  return BI && BI->isUnconditional();
}

bool isEmptyInlineAsmCall(const CallBase *CB) {
  if (!CB)
    return false;
  const auto *Asm = dyn_cast<InlineAsm>(CB->getCalledOperand());
  return Asm && Asm->getAsmString().empty();
}

bool isDirectMemSanRuntimeCall(const CallBase *CB) {
  if (!CB)
    return false;

  const Function *Callee = CB->getCalledFunction();
  if (!Callee || Callee->getName().empty())
    return false;

  StringRef Name = Callee->getName();
  Name.consume_front("\01");
  if (Name.starts_with("___msan_"))
    Name = Name.drop_front();
  return Name.starts_with("__msan_");
}

BasicBlock *getReportBlockFallthrough(BasicBlock *BB) {
  auto *BI = dyn_cast<BranchInst>(BB->getTerminator());
  if (!BI || !BI->isUnconditional())
    return nullptr;
  return BI->getSuccessor(0);
}

bool hasNonSanitizerPredecessor(BasicBlock *BB,
                                const SmallPtrSetImpl<BasicBlock *> &Blocks) {
  for (BasicBlock *Pred : predecessors(BB))
    if (!Blocks.contains(Pred))
      return true;
  return false;
}

} // namespace

CheckSliceRemover::CheckSliceRemover(Module &M) : M(M) {}

CheckSlice CheckSliceRemover::collectCheckSlice(CallBase *CB) {
  CheckSlice Slice;
  if (!CB)
    return Slice;

  addInstruction(Slice, CB);
  collectBackwardFromInstruction(Slice, CB);

  if (isSanitizerOnlyBlock(CB->getParent(), CB))
    addBlock(Slice, CB->getParent());

  collectControlFlowSlice(Slice, CB);
  return Slice;
}

bool CheckSliceRemover::isSanitizerOnlyInstruction(Instruction *I) const {
  if (!I)
    return false;

  if (auto *CB = dyn_cast<CallBase>(I)) {
    if (Collector.classifyCheck(CB))
      return true;
    if (isDirectMemSanRuntimeCall(CB))
      return true;
    if (isEmptyInlineAsmCall(CB))
      return true;
    return isNoopIntrinsic(I);
  }

  if (isa<BranchInst>(I) || isa<UnreachableInst>(I))
    return true;

  if (auto *Load = dyn_cast<LoadInst>(I))
    return !Load->isVolatile() && !Load->isAtomic();

  if (isa<StoreInst>(I) || isa<AtomicRMWInst>(I) ||
      isa<AtomicCmpXchgInst>(I))
    return false;

  if (isa<AllocaInst>(I))
    return false;

  if (I->mayHaveSideEffects())
    return false;

  return isa<CastInst>(I) || isa<GetElementPtrInst>(I) || isa<CmpInst>(I) ||
         isa<BinaryOperator>(I) || isa<SelectInst>(I) || isa<PHINode>(I) ||
         isa<ExtractValueInst>(I) || isa<InsertValueInst>(I) ||
         isa<UnaryOperator>(I);
}

bool CheckSliceRemover::removeCheckSlice(CheckNode *N) {
  if (!N || !N->CheckInst)
    return false;

  CallBase *CB = N->CheckInst;
  Function *F = CB->getFunction();
  if (F)
    TouchedFunctions.insert(F);

  CheckSlice Slice = collectCheckSlice(CB);
  bool RemovedCheck = bypassReportBlock(Slice, CB);

  if (RemovedCheck) {
    cleanupDeadInstructions();
    simplifyCFG();
    return true;
  }

  if (!RemovedCheck)
    RemovedCheck = eraseDirectCheckCall(CB);

  if (!RemovedCheck)
    return false;

  eraseDeadSliceInstructions(Slice);
  cleanupDeadInstructions();
  simplifyCFG();
  return true;
}

std::size_t CheckSliceRemover::cleanupDeadInstructions() {
  std::size_t DeadCount = 0;

  while (true) {
    SmallVector<WeakTrackingVH, 64> DeadInsts;

    for (Function *F : TouchedFunctions) {
      if (!F || F->isDeclaration())
        continue;
      for (BasicBlock &BB : *F)
        for (Instruction &I : BB)
          if (isInstructionTriviallyDead(&I))
            DeadInsts.push_back(&I);
    }

    if (DeadInsts.empty())
      break;

    DeadCount += DeadInsts.size();
    RecursivelyDeleteTriviallyDeadInstructions(DeadInsts);
  }

  return DeadCount;
}

bool CheckSliceRemover::simplifyCFG() {
  bool Changed = false;

  for (Function *F : TouchedFunctions) {
    if (!F || F->isDeclaration())
      continue;

    Changed |= EliminateUnreachableBlocks(*F);

    bool LocalChanged = true;
    while (LocalChanged) {
      LocalChanged = false;
      for (BasicBlock &BB : make_early_inc_range(*F)) {
        if (&BB == &F->getEntryBlock())
          continue;
        if (MergeBlockIntoPredecessor(&BB)) {
          Changed = true;
          LocalChanged = true;
          break;
        }
      }
    }
  }

  return Changed;
}

bool CheckSliceRemover::addInstruction(CheckSlice &Slice, Instruction *I) {
  if (!I || !isSanitizerOnlyInstruction(I))
    return false;

  if (!Slice.Instructions.insert(I).second)
    return false;

  Slice.OrderedInstructions.push_back(I);
  if (Function *F = I->getFunction())
    TouchedFunctions.insert(F);
  return true;
}

bool CheckSliceRemover::addBlock(CheckSlice &Slice, BasicBlock *BB) {
  if (!BB)
    return false;

  if (!Slice.Blocks.insert(BB).second)
    return false;

  Slice.OrderedBlocks.push_back(BB);
  if (Function *F = BB->getParent())
    TouchedFunctions.insert(F);

  for (Instruction &I : *BB)
    addInstruction(Slice, &I);
  return true;
}

void CheckSliceRemover::collectBackwardFromInstruction(CheckSlice &Slice,
                                                       Instruction *I) {
  if (!I)
    return;

  Function *F = I->getFunction();
  for (Use &Op : I->operands())
    collectBackwardFromValue(Slice, Op.get(), F);
}

void CheckSliceRemover::collectBackwardFromValue(CheckSlice &Slice, Value *V,
                                                 Function *F) {
  auto *OpI = dyn_cast_or_null<Instruction>(V);
  if (!OpI || OpI->getFunction() != F)
    return;

  if (!addInstruction(Slice, OpI))
    return;

  collectBackwardFromInstruction(Slice, OpI);
}

void CheckSliceRemover::collectControlFlowSlice(CheckSlice &Slice,
                                                CallBase *CB) {
  if (!CB)
    return;

  SmallVector<BasicBlock *, 8> Worklist;
  SmallPtrSet<BasicBlock *, 8> SeenBlocks;
  Worklist.push_back(CB->getParent());

  while (!Worklist.empty()) {
    BasicBlock *BB = Worklist.pop_back_val();
    if (!BB || !SeenBlocks.insert(BB).second)
      continue;

    for (BasicBlock *Pred : predecessors(BB)) {
      Instruction *Term = Pred->getTerminator();
      if (!isSanitizerOnlyInstruction(Term))
        continue;

      addInstruction(Slice, Term);
      collectBackwardFromInstruction(Slice, Term);

      if (isSanitizerOnlyBlock(Pred, CB)) {
        addBlock(Slice, Pred);
        Worklist.push_back(Pred);
      }
    }
  }
}

bool CheckSliceRemover::isSanitizerOnlyBlock(BasicBlock *BB,
                                             CallBase *TargetCB) const {
  if (!BB)
    return false;

  for (Instruction &I : *BB) {
    if (auto *CB = dyn_cast<CallBase>(&I))
      if (Collector.classifyCheck(CB) && CB != TargetCB)
        return false;
    if (!isSanitizerOnlyInstruction(&I))
      return false;
  }
  return true;
}

bool CheckSliceRemover::canEraseInstruction(Instruction *I,
                                            const CheckSlice &Slice) const {
  if (!I || !I->getParent())
    return false;
  if (!Slice.Instructions.contains(I))
    return false;
  if (I->isTerminator())
    return false;
  if (!allUsersInsideSlice(I, Slice))
    return false;
  if (!I->use_empty())
    return false;

  if (auto *CB = dyn_cast<CallBase>(I))
    return Collector.classifyCheck(CB) || isDirectMemSanRuntimeCall(CB) ||
           isNoopIntrinsic(I);

  if (auto *Load = dyn_cast<LoadInst>(I))
    return !Load->isVolatile() && !Load->isAtomic();

  return isSanitizerOnlyInstruction(I) && !I->mayHaveSideEffects();
}

bool CheckSliceRemover::allUsersInsideSlice(Instruction *I,
                                            const CheckSlice &Slice) const {
  for (User *U : I->users()) {
    auto *UserI = dyn_cast<Instruction>(U);
    if (!UserI || !Slice.Instructions.contains(UserI))
      return false;
  }
  return true;
}

bool CheckSliceRemover::bypassReportBlock(CheckSlice &Slice, CallBase *CB) {
  if (!CB)
    return false;

  BasicBlock *ReportBB = CB->getParent();
  if (!ReportBB || !isSanitizerOnlyBlock(ReportBB, CB))
    return false;

  auto *ReportTerm = ReportBB->getTerminator();
  if (!isReportBlockTerminator(ReportTerm))
    return false;

  BasicBlock *Fallthrough = getReportBlockFallthrough(ReportBB);
  SmallVector<BasicBlock *, 8> Preds(predecessors(ReportBB));

  for (BasicBlock *Pred : Preds) {
    auto *BI = dyn_cast<BranchInst>(Pred->getTerminator());
    if (!BI)
      return false;

    BasicBlock *SafeSucc = nullptr;
    if (BI->isConditional()) {
      BasicBlock *OtherSucc = nullptr;
      if (BI->getSuccessor(0) == ReportBB)
        OtherSucc = BI->getSuccessor(1);
      else if (BI->getSuccessor(1) == ReportBB)
        OtherSucc = BI->getSuccessor(0);
      else
        return false;

      if (Fallthrough && OtherSucc != Fallthrough)
        return false;
      SafeSucc = Fallthrough ? Fallthrough : OtherSucc;
    } else if (BI->isUnconditional()) {
      if (!Fallthrough)
        return false;
      SafeSucc = Fallthrough;
    }

    if (!SafeSucc || SafeSucc == ReportBB)
      return false;
  }

  for (BasicBlock *Pred : Preds) {
    auto *BI = cast<BranchInst>(Pred->getTerminator());
    BasicBlock *SafeSucc = nullptr;

    if (BI->isConditional()) {
      BasicBlock *OtherSucc = BI->getSuccessor(0) == ReportBB
                                  ? BI->getSuccessor(1)
                                  : BI->getSuccessor(0);
      SafeSucc = Fallthrough ? Fallthrough : OtherSucc;
    } else {
      SafeSucc = Fallthrough;
    }

    collectBackwardFromInstruction(Slice, BI);
    ReportBB->removePredecessor(Pred, false);
    BranchInst::Create(SafeSucc, BI);
    BI->eraseFromParent();
  }

  if (hasNonSanitizerPredecessor(ReportBB, Slice.Blocks))
    return false;

  if (!pred_empty(ReportBB))
    return false;

  DeleteDeadBlock(ReportBB);
  return true;
}

bool CheckSliceRemover::eraseDirectCheckCall(CallBase *CB) {
  auto *CI = dyn_cast_or_null<CallInst>(CB);
  if (!CI || !CI->use_empty())
    return false;

  TouchedFunctions.insert(CI->getFunction());
  CI->eraseFromParent();
  return true;
}

std::size_t CheckSliceRemover::eraseDeadSliceInstructions(CheckSlice &Slice) {
  std::size_t Removed = 0;
  bool Changed = true;

  while (Changed) {
    Changed = false;
    for (Instruction *I : llvm::reverse(Slice.OrderedInstructions)) {
      if (!canEraseInstruction(I, Slice))
        continue;

      I->eraseFromParent();
      ++Removed;
      Changed = true;
    }
  }

  return Removed;
}

} // namespace desan
