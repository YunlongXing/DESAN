#include "DESAN/CheckedVariableAnalyzer.h"

#include "llvm/ADT/ArrayRef.h"
#include "llvm/ADT/STLExtras.h"
#include "llvm/ADT/SmallPtrSet.h"
#include "llvm/ADT/SmallVector.h"
#include "llvm/ADT/StringRef.h"
#include "llvm/IR/BasicBlock.h"
#include "llvm/IR/CFG.h"
#include "llvm/IR/Constants.h"
#include "llvm/IR/DataLayout.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/GlobalValue.h"
#include "llvm/IR/InstrTypes.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/IntrinsicInst.h"
#include "llvm/IR/Module.h"
#include "llvm/IR/Operator.h"
#include "llvm/IR/Value.h"
#include "llvm/Support/raw_ostream.h"

#include <cctype>
#include <cstddef>
#include <cstdint>
#include <iterator>
#include <optional>

using namespace llvm;

namespace desan {

namespace {

constexpr unsigned MaxTraceDepth = 32;
constexpr unsigned MaxUseTraceDepth = 12;

StringRef getCheckType(const SanitizerCheckCollector::ClassifiedCheck &Check) {
  return Check.CheckType;
}

bool isLoadCheckName(StringRef Name) {
  return Name.starts_with("__asan_report_load") ||
         Name.starts_with("__asan_report_exp_load") ||
         Name.starts_with("__asan_load") ||
         Name.starts_with("__asan_exp_load");
}

bool isStoreCheckName(StringRef Name) {
  return Name.starts_with("__asan_report_store") ||
         Name.starts_with("__asan_report_exp_store") ||
         Name.starts_with("__asan_store") ||
         Name.starts_with("__asan_exp_store");
}

bool isMemWriteCheckName(StringRef Name) {
  return Name.starts_with("__asan_memset");
}

bool isTypeMismatchCheck(StringRef Name) {
  return Name.starts_with("__ubsan_handle_type_mismatch");
}

bool isPointerOverflowCheck(StringRef Name) {
  return Name.starts_with("__ubsan_handle_pointer_overflow");
}

bool isOutOfBoundsCheck(StringRef Name) {
  return Name.starts_with("__ubsan_handle_out_of_bounds");
}

bool isShiftOutOfBoundsCheck(StringRef Name) {
  return Name.starts_with("__ubsan_handle_shift_out_of_bounds");
}

bool isMemSanExplicitValueCheck(StringRef Name) {
  return Name.starts_with("__msan_param_") ||
         Name.starts_with("__msan_retval_") ||
         Name.starts_with("__msan_va_arg_") ||
         Name.starts_with("__msan_check_mem_is_initialized") ||
         Name.starts_with("__msan_test_shadow") ||
         Name.starts_with("__msan_print_shadow") ||
         Name.starts_with("__msan_maybe_warning");
}

bool isMemSanMemoryRegionCheck(StringRef Name) {
  return Name.starts_with("__msan_check_mem_is_initialized") ||
         Name.starts_with("__msan_test_shadow") ||
         Name.starts_with("__msan_print_shadow");
}

bool isMemSanValueUseCheck(StringRef Name) {
  return Name.starts_with("__msan_param_") ||
         Name.starts_with("__msan_retval_") ||
         Name.starts_with("__msan_va_arg_") ||
         Name.starts_with("__msan_maybe_warning");
}

bool isMemSanWarningCheck(StringRef Name) {
  return Name.starts_with("__msan_warning");
}

void appendOffset(SmallVectorImpl<Value *> &Offsets, Value *V) {
  if (!V)
    return;
  Offsets.push_back(V);
}

void appendOffsets(SmallVectorImpl<Value *> &Offsets,
                   ArrayRef<Value *> MoreOffsets) {
  Offsets.append(MoreOffsets.begin(), MoreOffsets.end());
}

bool sameOffsets(ArrayRef<Value *> LHS, ArrayRef<Value *> RHS) {
  if (LHS.size() != RHS.size())
    return false;
  for (auto [LHSOffset, RHSOffset] : zip(LHS, RHS))
    if (LHSOffset != RHSOffset)
      return false;
  return true;
}

bool sameRegionStart(const CheckedVariable &LHS,
                     const CheckedVariable &RHS) {
  if (LHS.HasStaticByteOffset != RHS.HasStaticByteOffset)
    return false;
  if (!LHS.HasStaticByteOffset)
    return true;
  return LHS.StaticByteOffset == RHS.StaticByteOffset;
}

SmallPtrSet<Value *, 16>
cloneVisited(const SmallPtrSetImpl<Value *> &Visited) {
  SmallPtrSet<Value *, 16> Copy;
  for (Value *V : Visited)
    Copy.insert(V);
  return Copy;
}

Value *firstNonConstant(Value *LHS, Value *RHS) {
  if (LHS && !isa<Constant>(LHS))
    return LHS;
  if (RHS && !isa<Constant>(RHS))
    return RHS;
  return LHS ? LHS : RHS;
}

Value *stripScalarCasts(Value *V, unsigned Depth = 0) {
  if (!V || Depth > MaxTraceDepth)
    return V;

  if (auto *Cast = dyn_cast<CastInst>(V))
    return stripScalarCasts(Cast->getOperand(0), Depth + 1);

  if (auto *Cast = dyn_cast<ConstantExpr>(V))
    if (Cast->isCast())
      return stripScalarCasts(Cast->getOperand(0), Depth + 1);

  return V;
}

bool sameScalarRoot(Value *LHS, Value *RHS) {
  return stripScalarCasts(LHS) == stripScalarCasts(RHS);
}

bool isTraceThroughInstruction(const User *User) {
  return isa<GetElementPtrInst>(User) || isa<BitCastInst>(User) ||
         isa<AddrSpaceCastInst>(User) || isa<PtrToIntInst>(User) ||
         isa<IntToPtrInst>(User) || isa<PHINode>(User) ||
         isa<SelectInst>(User);
}

std::optional<uint64_t> parseDecimalAfterToken(StringRef Name,
                                               StringRef Token) {
  std::size_t Pos = Name.find(Token);
  if (Pos == StringRef::npos)
    return std::nullopt;

  StringRef Tail = Name.drop_front(Pos + Token.size());
  uint64_t Result = 0;
  bool SawDigit = false;
  while (!Tail.empty() &&
         std::isdigit(static_cast<unsigned char>(Tail.front()))) {
    SawDigit = true;
    Result = Result * 10 + static_cast<uint64_t>(Tail.front() - '0');
    Tail = Tail.drop_front();
  }

  if (!SawDigit)
    return std::nullopt;
  return Result;
}

uint64_t getConstantSizeOperand(CallBase *CB) {
  if (!CB || CB->arg_size() < 2)
    return 0;
  auto *Size = dyn_cast<ConstantInt>(CB->getArgOperand(1));
  if (!Size)
    return 0;
  return Size->getZExtValue();
}

void markUnknownStaticOffset(CheckedVariable &Var) {
  Var.HasStaticByteOffset = false;
  Var.StaticByteOffset = 0;
}

void addStaticOffset(CheckedVariable &Var, int64_t Delta) {
  if (!Var.HasStaticByteOffset)
    return;
  Var.StaticByteOffset += Delta;
}

template <typename GEPKind>
void appendGEPRegion(CheckedVariable &Var, const GEPKind *GEP,
                     const DataLayout *DL) {
  if (!GEP) {
    markUnknownStaticOffset(Var);
    return;
  }

  for (Value *Index : GEP->indices())
    appendOffset(Var.Offsets, Index);

  if (!DL || !Var.HasStaticByteOffset) {
    markUnknownStaticOffset(Var);
    return;
  }

  APInt Offset(DL->getIndexTypeSizeInBits(GEP->getType()), 0);
  if (!GEP->accumulateConstantOffset(*DL, Offset) ||
      !Offset.isSignedIntN(64)) {
    markUnknownStaticOffset(Var);
    return;
  }

  addStaticOffset(Var, Offset.getSExtValue());
}

CheckedVariable makeBaseVariable(Value *V) {
  CheckedVariable Result;
  Result.Base = V;
  if (V && V->getType()->isPointerTy())
    Result.Address = V;
  Result.HasStaticByteOffset = true;
  Result.StaticByteOffset = 0;
  return Result;
}

Value *recoverAddressPointer(Value *V, unsigned Depth = 0) {
  if (!V || Depth > MaxTraceDepth)
    return nullptr;

  if (V->getType()->isPointerTy())
    return V->stripPointerCasts();

  if (auto *Cast = dyn_cast<CastInst>(V))
    return recoverAddressPointer(Cast->getOperand(0), Depth + 1);

  if (auto *Cast = dyn_cast<ConstantExpr>(V))
    if (Cast->isCast())
      return recoverAddressPointer(Cast->getOperand(0), Depth + 1);

  if (auto *BinOp = dyn_cast<BinaryOperator>(V)) {
    Value *LHS = recoverAddressPointer(BinOp->getOperand(0), Depth + 1);
    if (LHS)
      return LHS;
    return recoverAddressPointer(BinOp->getOperand(1), Depth + 1);
  }

  return nullptr;
}

Value *getMemIntrinsicDest(Value *V) {
  if (auto *MTI = dyn_cast<MemTransferInst>(V))
    return MTI->getRawDest();
  if (auto *MSI = dyn_cast<MemSetInst>(V))
    return MSI->getRawDest();
  return nullptr;
}

Value *getMemIntrinsicSource(Value *V) {
  if (auto *MTI = dyn_cast<MemTransferInst>(V))
    return MTI->getRawSource();
  return nullptr;
}

uint64_t constantMemIntrinsicLength(Value *V) {
  if (auto *MTI = dyn_cast<MemIntrinsic>(V))
    if (auto *Len = dyn_cast<ConstantInt>(MTI->getLength()))
      return Len->getZExtValue();
  return 0;
}

template <typename GEPKind>
bool gepUsesIndex(const GEPKind *GEP, Value *Index) {
  if (!GEP || !Index)
    return false;

  for (Value *GEPIndex : GEP->indices())
    if (sameScalarRoot(GEPIndex, Index))
      return true;
  return false;
}

const DataLayout *dataLayoutForValue(Value *V) {
  if (!V)
    return nullptr;
  if (auto *I = dyn_cast<Instruction>(V))
    if (Module *M = I->getModule())
      return &M->getDataLayout();
  if (auto *A = dyn_cast<Argument>(V))
    if (Function *F = A->getParent())
      if (Module *M = F->getParent())
        return &M->getDataLayout();
  if (auto *GV = dyn_cast<GlobalValue>(V))
    if (Module *M = GV->getParent())
      return &M->getDataLayout();
  return nullptr;
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

uint64_t typeStoreSizeOrZero(const DataLayout *DL, Type *Ty) {
  if (!DL || !Ty || !Ty->isSized())
    return 0;
  return DL->getTypeStoreSize(Ty);
}

uint64_t inferSizeFromValueDef(Value *V, const DataLayout *DL,
                               unsigned Depth = 0) {
  if (!V || !DL || Depth > MaxTraceDepth)
    return 0;

  V = stripScalarCasts(V);

  if (auto *Load = dyn_cast<LoadInst>(V))
    return typeStoreSizeOrZero(DL, Load->getType());

  if (auto *Store = dyn_cast<StoreInst>(V))
    return typeStoreSizeOrZero(DL, Store->getValueOperand()->getType());

  if (auto *Cmp = dyn_cast<CmpInst>(V)) {
    Value *Operand = firstNonConstant(Cmp->getOperand(0), Cmp->getOperand(1));
    if (uint64_t Size = inferSizeFromValueDef(Operand, DL, Depth + 1))
      return Size;
  }

  if (auto *BinOp = dyn_cast<BinaryOperator>(V)) {
    Value *Operand =
        firstNonConstant(BinOp->getOperand(0), BinOp->getOperand(1));
    if (uint64_t Size = inferSizeFromValueDef(Operand, DL, Depth + 1))
      return Size;
  }

  if (auto *Phi = dyn_cast<PHINode>(V)) {
    uint64_t CommonSize = 0;
    for (Value *Incoming : Phi->incoming_values()) {
      uint64_t IncomingSize = inferSizeFromValueDef(Incoming, DL, Depth + 1);
      if (IncomingSize == 0)
        continue;
      if (CommonSize != 0 && CommonSize != IncomingSize)
        return 0;
      CommonSize = IncomingSize;
    }
    if (CommonSize != 0)
      return CommonSize;
  }

  if (auto *Select = dyn_cast<SelectInst>(V)) {
    uint64_t TrueSize =
        inferSizeFromValueDef(Select->getTrueValue(), DL, Depth + 1);
    uint64_t FalseSize =
        inferSizeFromValueDef(Select->getFalseValue(), DL, Depth + 1);
    if (TrueSize != 0 && TrueSize == FalseSize)
      return TrueSize;
  }

  return typeStoreSizeOrZero(DL, V->getType());
}

} // namespace

StringRef accessTypeName(AccessType Type) {
  switch (Type) {
  case AccessType::READ:
    return "READ";
  case AccessType::WRITE:
    return "WRITE";
  case AccessType::UNKNOWN:
    return "UNKNOWN";
  }
  return "UNKNOWN";
}

std::optional<CheckedVariable>
CheckedVariableAnalyzer::analyzeCheck(CallBase *CB) {
  std::optional<ClassifiedCheck> Check = classifyCheck(CB);
  if (!Check)
    return std::nullopt;

  CurrentDL = CB && CB->getModule() ? &CB->getModule()->getDataLayout()
                                    : nullptr;

  CheckedVariable Result;
  Value *CheckedValue = getCheckedOperand(CB, *Check);
  if (CheckedValue) {
    if (Check->Sanitizer == SanitizerKind::ASan) {
      Result = traceASanCheckedAddress(CheckedValue);
      Result.Address = recoverAddressPointer(CheckedValue);
    } else {
      Result = traceCheckedValue(CheckedValue);
      if (!Result.Address)
        Result.Address = recoverAddressPointer(CheckedValue);
      if (!Result.Address && CheckedValue->getType()->isPointerTy())
        Result.Address = CheckedValue->stripPointerCasts();
    }
  }

  Result.Type = inferAccessType(CB);
  Result.Sanitizer = Check->Sanitizer;
  if (Check->Sanitizer == SanitizerKind::ASan)
    Result.AccessSize = inferASanAccessSize(CB, Check->CheckType);
  else if (Check->Sanitizer == SanitizerKind::UBSan) {
    if (CheckedValue)
      Result.AccessSize = inferAccessSizeFromUses(CheckedValue);
    if (Result.AccessSize == 0 && Result.Address)
      Result.AccessSize = inferAccessSizeFromUses(Result.Address);
  } else if (Check->Sanitizer == SanitizerKind::MemSan) {
    Result.AccessSize = inferMemSanAccessSize(CB, Check->CheckType,
                                              CheckedValue);
    if (Result.AccessSize == 0 && Result.Address)
      Result.AccessSize = inferAccessSizeFromUses(Result.Address);
  }
  Result.CheckInst = CB;
  return Result;
}

CheckedVariable CheckedVariableAnalyzer::traceCheckedValue(Value *V) {
  if (const DataLayout *DL = dataLayoutForValue(V))
    CurrentDL = DL;
  SmallPtrSet<Value *, 16> Visited;
  return traceCheckedValueImpl(V, Visited, 0);
}

Value *CheckedVariableAnalyzer::normalizeVariable(Value *V) {
  SmallPtrSet<Value *, 16> Visited;
  return normalizeVariableImpl(V, Visited, 0);
}

AccessType CheckedVariableAnalyzer::inferAccessType(CallBase *CB) {
  std::optional<ClassifiedCheck> Check = classifyCheck(CB);
  if (!Check)
    return AccessType::UNKNOWN;

  StringRef CheckType = getCheckType(*Check);
  switch (Check->Sanitizer) {
  case SanitizerKind::ASan:
    if (isLoadCheckName(CheckType))
      return AccessType::READ;
    if (isStoreCheckName(CheckType) || isMemWriteCheckName(CheckType))
      return AccessType::WRITE;
    return AccessType::UNKNOWN;

  case SanitizerKind::UBSan:
    if (isShiftOutOfBoundsCheck(CheckType))
      return AccessType::UNKNOWN;
    if (Value *CheckedValue = getCheckedOperand(CB, *Check)) {
      AccessType Type = inferAccessTypeFromUses(CheckedValue, CB);
      if (Type != AccessType::UNKNOWN)
        return Type;

      if (Value *RecoveredPointer = recoverAddressPointer(CheckedValue)) {
        Type = inferAccessTypeFromUses(RecoveredPointer, CB);
        if (Type != AccessType::UNKNOWN)
          return Type;
      }
    }
    return AccessType::UNKNOWN;

  case SanitizerKind::MemSan:
    if (isMemSanMemoryRegionCheck(CheckType) ||
        isMemSanValueUseCheck(CheckType))
      return AccessType::READ;
    if (isMemSanWarningCheck(CheckType) && getCheckedOperand(CB, *Check))
      return AccessType::READ;
    if (Value *CheckedValue = getCheckedOperand(CB, *Check))
      return inferAccessTypeFromUses(CheckedValue, CB);
    return AccessType::UNKNOWN;

  case SanitizerKind::Unknown:
    return AccessType::UNKNOWN;
  }

  return AccessType::UNKNOWN;
}

std::optional<CheckedVariableAnalyzer::ClassifiedCheck>
CheckedVariableAnalyzer::classifyCheck(CallBase *CB) const {
  return Collector.classifyCheck(CB);
}

Value *CheckedVariableAnalyzer::getCheckedOperand(
    CallBase *CB, const ClassifiedCheck &Check) const {
  if (!CB)
    return nullptr;

  StringRef CheckType = getCheckType(Check);
  switch (Check.Sanitizer) {
  case SanitizerKind::ASan:
    if (CB->arg_size() > 0)
      return CB->getArgOperand(0);
    return nullptr;

  case SanitizerKind::UBSan:
    return getUBSanCheckedOperand(CB, CheckType);

  case SanitizerKind::MemSan:
    if (isMemSanExplicitValueCheck(CheckType) && CB->arg_size() > 0)
      return CB->getArgOperand(0);
    return getImplicitMemSanOperand(CB, CheckType);

  case SanitizerKind::Unknown:
    return nullptr;
  }

  return nullptr;
}

Value *CheckedVariableAnalyzer::getUBSanCheckedOperand(
    CallBase *CB, StringRef CheckType) const {
  if (!CB)
    return nullptr;

  if (isTypeMismatchCheck(CheckType) && CB->arg_size() > 1)
    return CB->getArgOperand(1);

  if (isPointerOverflowCheck(CheckType)) {
    Value *Base = CB->arg_size() > 1 ? CB->getArgOperand(1) : nullptr;
    Value *Result = CB->arg_size() > 2 ? CB->getArgOperand(2) : nullptr;
    if (Result && recoverAddressPointer(Result))
      return Result;
    if (Base && recoverAddressPointer(Base))
      return Base;
    if (Result)
      return Result;
    if (Base)
      return Base;
    return nullptr;
  }

  if (isOutOfBoundsCheck(CheckType) && CB->arg_size() > 1) {
    Value *Index = CB->getArgOperand(1);
    if (Value *Access = findUBSanOutOfBoundsAccessOperand(CB, Index))
      return Access;
    return Index;
  }

  if (isShiftOutOfBoundsCheck(CheckType)) {
    if (CB->arg_size() > 1)
      return CB->getArgOperand(1);
    return nullptr;
  }

  if (CB->arg_size() > 1)
    return CB->getArgOperand(1);
  return nullptr;
}

Value *CheckedVariableAnalyzer::findUBSanOutOfBoundsAccessOperand(
    CallBase *CB, Value *Index) const {
  if (!CB || !Index)
    return nullptr;

  Function *F = CB->getFunction();
  if (!F)
    return nullptr;

  auto MatchesIndex = [Index](Instruction &I) -> Value * {
    if (auto *GEP = dyn_cast<GetElementPtrInst>(&I))
      if (gepUsesIndex(GEP, Index))
        return GEP;
    return nullptr;
  };

  BasicBlock *ReportBB = CB->getParent();
  if (!ReportBB)
    return nullptr;

  unsigned InsnBudget = 96;
  for (auto It = std::next(CB->getIterator()), End = ReportBB->end();
       It != End && InsnBudget != 0; ++It, --InsnBudget) {
    if (Value *Access = MatchesIndex(*It))
      return Access;
  }

  SmallVector<BasicBlock *, 8> Worklist;
  SmallPtrSet<BasicBlock *, 16> Seen;
  for (BasicBlock *Succ : successors(ReportBB))
    Worklist.push_back(Succ);

  unsigned BlockBudget = 8;
  while (!Worklist.empty() && BlockBudget-- != 0 && InsnBudget != 0) {
    BasicBlock *BB = Worklist.pop_back_val();
    if (!BB || BB->getParent() != F || !Seen.insert(BB).second)
      continue;

    for (Instruction &I : *BB) {
      if (InsnBudget-- == 0)
        break;
      if (Value *Access = MatchesIndex(I))
        return Access;
    }

    for (BasicBlock *Succ : successors(BB))
      if (!Seen.contains(Succ))
        Worklist.push_back(Succ);
  }

  return nullptr;
}

Value *CheckedVariableAnalyzer::getImplicitMemSanOperand(
    CallBase *CB, StringRef CheckType) const {
  if (!CB || !isMemSanWarningCheck(CheckType))
    return nullptr;

  BasicBlock *BB = CB->getParent();
  if (!BB)
    return nullptr;

  for (auto It = CB->getIterator(); It != BB->begin();) {
    --It;
    Instruction &Candidate = *It;
    if (isa<DbgInfoIntrinsic>(&Candidate))
      continue;

    if (auto *PrevCB = dyn_cast<CallBase>(&Candidate)) {
      if (Collector.classifyCheck(PrevCB) ||
          isDirectMemSanRuntimeCall(PrevCB))
        continue;
      return nullptr;
    }

    if (Candidate.isTerminator())
      continue;
    if (Candidate.mayHaveSideEffects() && !isa<LoadInst>(&Candidate))
      return nullptr;

    return &Candidate;
  }

  if (BasicBlock *Pred = BB->getSinglePredecessor()) {
    if (auto *BI = dyn_cast<BranchInst>(Pred->getTerminator()))
      if (BI->isConditional())
        return BI->getCondition();
  }

  return nullptr;
}

uint64_t CheckedVariableAnalyzer::inferMemSanAccessSize(
    CallBase *CB, StringRef CheckType, Value *CheckedValue) {
  if (isMemSanMemoryRegionCheck(CheckType))
    if (uint64_t Size = getConstantSizeOperand(CB))
      return Size;

  const DataLayout *DL =
      CurrentDL ? CurrentDL : dataLayoutForValue(CheckedValue);
  if (!DL)
    return 0;

  if (isMemSanMemoryRegionCheck(CheckType))
    return 0;

  if (CheckedValue) {
    if (uint64_t Size = inferSizeFromValueDef(CheckedValue, DL))
      return Size;

    if (uint64_t Size = inferAccessSizeFromUses(CheckedValue))
      return Size;
  }

  return 0;
}

uint64_t CheckedVariableAnalyzer::inferASanAccessSize(
    CallBase *CB, StringRef CheckType) const {
  if (std::optional<uint64_t> LoadSize =
          parseDecimalAfterToken(CheckType, "load"))
    return *LoadSize;
  if (std::optional<uint64_t> StoreSize =
          parseDecimalAfterToken(CheckType, "store"))
    return *StoreSize;

  if (CheckType.contains("loadN") || CheckType.contains("storeN") ||
      CheckType.contains("load_n") || CheckType.contains("store_n"))
    return getConstantSizeOperand(CB);

  return 0;
}

uint64_t CheckedVariableAnalyzer::inferAccessSizeFromUses(Value *CheckedValue) {
  if (!CheckedValue)
    return 0;

  const DataLayout *DL = CurrentDL ? CurrentDL : dataLayoutForValue(CheckedValue);
  if (!DL)
    return 0;

  SmallVector<Value *, 16> Worklist;
  SmallPtrSet<Value *, 32> Visited;
  Worklist.push_back(CheckedValue);

  for (unsigned Depth = 0; !Worklist.empty() && Depth < MaxUseTraceDepth;
       ++Depth) {
    SmallVector<Value *, 16> NextWorklist;
    for (Value *Current : Worklist) {
      if (!Current || !Visited.insert(Current).second)
        continue;

      Value *NormalizedCurrent = normalizeVariable(Current);
      for (User *U : Current->users()) {
        if (auto *Load = dyn_cast<LoadInst>(U)) {
          if (normalizeVariable(Load->getPointerOperand()) ==
              NormalizedCurrent)
            return DL->getTypeStoreSize(Load->getType());
        } else if (auto *Store = dyn_cast<StoreInst>(U)) {
          if (normalizeVariable(Store->getPointerOperand()) ==
              NormalizedCurrent)
            return DL->getTypeStoreSize(Store->getValueOperand()->getType());
        } else if (Value *Dest = getMemIntrinsicDest(U)) {
          if (normalizeVariable(Dest) == NormalizedCurrent)
            if (uint64_t Size = constantMemIntrinsicLength(U))
              return Size;
          if (Value *Src = getMemIntrinsicSource(U))
            if (normalizeVariable(Src) == NormalizedCurrent)
              if (uint64_t Size = constantMemIntrinsicLength(U))
                return Size;
        } else if (isTraceThroughInstruction(U)) {
          NextWorklist.push_back(U);
        }
      }
    }
    Worklist.swap(NextWorklist);
  }

  return 0;
}

CheckedVariable CheckedVariableAnalyzer::traceASanCheckedAddress(Value *V) {
  SmallPtrSet<Value *, 16> Visited;
  return traceASanCheckedAddressImpl(V, Visited, 0);
}

CheckedVariable CheckedVariableAnalyzer::traceASanCheckedAddressImpl(
    Value *V, SmallPtrSetImpl<Value *> &Visited, unsigned Depth) {
  CheckedVariable Result;
  if (!V)
    return Result;

  if (Depth > MaxTraceDepth || !Visited.insert(V).second) {
    return makeBaseVariable(V);
  }

  V = V->stripPointerCasts();

  if (auto *GEP = dyn_cast<GetElementPtrInst>(V)) {
    Result = traceASanCheckedAddressImpl(GEP->getPointerOperand(), Visited,
                                         Depth + 1);
    appendGEPRegion(Result, GEP, CurrentDL);
    Result.Address = GEP;
    return Result;
  }

  if (auto *GEP = dyn_cast<GEPOperator>(V)) {
    Result = traceASanCheckedAddressImpl(GEP->getPointerOperand(), Visited,
                                         Depth + 1);
    appendGEPRegion(Result, GEP, CurrentDL);
    Result.Address = GEP;
    return Result;
  }

  if (auto *Load = dyn_cast<LoadInst>(V)) {
    Result = traceASanCheckedAddressImpl(Load->getPointerOperand(), Visited,
                                         Depth + 1);
    markUnknownStaticOffset(Result);
    return Result;
  }

  if (auto *Cast = dyn_cast<CastInst>(V))
    return traceASanCheckedAddressImpl(Cast->getOperand(0), Visited,
                                       Depth + 1);

  if (auto *Phi = dyn_cast<PHINode>(V)) {
    CheckedVariable Merged;
    bool HasIncoming = false;
    bool SameBase = true;

    for (Value *Incoming : Phi->incoming_values()) {
      SmallPtrSet<Value *, 16> IncomingVisited = cloneVisited(Visited);
      CheckedVariable IncomingVar =
          traceASanCheckedAddressImpl(Incoming, IncomingVisited, Depth + 1);
      if (!IncomingVar.Base)
        continue;

      Value *IncomingBase = normalizeVariable(IncomingVar.Base);
      if (!HasIncoming) {
        Merged.Base = IncomingBase;
        appendOffsets(Merged.Offsets, IncomingVar.Offsets);
        Merged.HasStaticByteOffset = IncomingVar.HasStaticByteOffset;
        Merged.StaticByteOffset = IncomingVar.StaticByteOffset;
        HasIncoming = true;
      } else if (Merged.Base != IncomingBase ||
                 !sameOffsets(Merged.Offsets, IncomingVar.Offsets) ||
                 !sameRegionStart(Merged, IncomingVar)) {
        SameBase = false;
      }
    }

    if (HasIncoming && SameBase)
      return Merged;

    Result.Base = Phi;
    return Result;
  }

  if (auto *Select = dyn_cast<SelectInst>(V)) {
    SmallPtrSet<Value *, 16> TrueVisited = cloneVisited(Visited);
    SmallPtrSet<Value *, 16> FalseVisited = cloneVisited(Visited);
    CheckedVariable TrueVar = traceASanCheckedAddressImpl(
        Select->getTrueValue(), TrueVisited, Depth + 1);
    CheckedVariable FalseVar = traceASanCheckedAddressImpl(
        Select->getFalseValue(), FalseVisited, Depth + 1);

    Value *TrueBase = normalizeVariable(TrueVar.Base);
    Value *FalseBase = normalizeVariable(FalseVar.Base);
    if (TrueBase && TrueBase == FalseBase) {
      if (!sameOffsets(TrueVar.Offsets, FalseVar.Offsets) ||
          !sameRegionStart(TrueVar, FalseVar)) {
        Result.Base = Select;
        return Result;
      }
      Result.Base = TrueBase;
      appendOffsets(Result.Offsets, TrueVar.Offsets);
      Result.HasStaticByteOffset = TrueVar.HasStaticByteOffset;
      Result.StaticByteOffset = TrueVar.StaticByteOffset;
      return Result;
    }

    Result.Base = Select;
    return Result;
  }

  if (auto *BinOp = dyn_cast<BinaryOperator>(V)) {
    Value *LHS = BinOp->getOperand(0);
    Value *RHS = BinOp->getOperand(1);
    Value *AddressOperand = firstNonConstant(LHS, RHS);
    Result = traceASanCheckedAddressImpl(AddressOperand, Visited, Depth + 1);

    if (BinOp->getOpcode() == Instruction::Add ||
        BinOp->getOpcode() == Instruction::Sub) {
      if (isa<Constant>(LHS)) {
        appendOffset(Result.Offsets, LHS);
        if (auto *CI = dyn_cast<ConstantInt>(LHS)) {
          if (BinOp->getOpcode() == Instruction::Sub)
            markUnknownStaticOffset(Result);
          else
            addStaticOffset(Result, CI->getSExtValue());
        } else {
          markUnknownStaticOffset(Result);
        }
      } else if (isa<Constant>(RHS)) {
        appendOffset(Result.Offsets, RHS);
        if (auto *CI = dyn_cast<ConstantInt>(RHS))
          addStaticOffset(Result, BinOp->getOpcode() == Instruction::Sub
                                      ? -CI->getSExtValue()
                                      : CI->getSExtValue());
        else
          markUnknownStaticOffset(Result);
      }
    }

    return Result;
  }

  return makeBaseVariable(normalizeVariable(V));
}

CheckedVariable CheckedVariableAnalyzer::traceCheckedValueImpl(
    Value *V, SmallPtrSetImpl<Value *> &Visited, unsigned Depth) {
  CheckedVariable Result;
  if (!V)
    return Result;

  if (Depth > MaxTraceDepth || !Visited.insert(V).second) {
    return makeBaseVariable(V);
  }

  V = V->stripPointerCasts();

  if (auto *GEP = dyn_cast<GetElementPtrInst>(V)) {
    Result = traceCheckedValueImpl(GEP->getPointerOperand(), Visited,
                                   Depth + 1);
    appendGEPRegion(Result, GEP, CurrentDL);
    Result.Address = GEP;
    return Result;
  }

  if (auto *Load = dyn_cast<LoadInst>(V)) {
    Result = traceCheckedValueImpl(Load->getPointerOperand(), Visited,
                                   Depth + 1);
    markUnknownStaticOffset(Result);
    return Result;
  }

  if (auto *Store = dyn_cast<StoreInst>(V)) {
    Result = traceCheckedValueImpl(Store->getPointerOperand(), Visited,
                                   Depth + 1);
    markUnknownStaticOffset(Result);
    return Result;
  }

  if (auto *Cast = dyn_cast<CastInst>(V))
    return traceCheckedValueImpl(Cast->getOperand(0), Visited, Depth + 1);

  if (auto *Cast = dyn_cast<ConstantExpr>(V))
    if (Cast->isCast())
      return traceCheckedValueImpl(Cast->getOperand(0), Visited, Depth + 1);

  if (auto *GEP = dyn_cast<GEPOperator>(V)) {
    Result = traceCheckedValueImpl(GEP->getPointerOperand(), Visited,
                                   Depth + 1);
    appendGEPRegion(Result, GEP, CurrentDL);
    Result.Address = GEP;
    return Result;
  }

  if (auto *Phi = dyn_cast<PHINode>(V)) {
    CheckedVariable Merged;
    bool HasIncoming = false;
    bool SameBase = true;

    for (Value *Incoming : Phi->incoming_values()) {
      SmallPtrSet<Value *, 16> IncomingVisited = cloneVisited(Visited);
      CheckedVariable IncomingVar =
          traceCheckedValueImpl(Incoming, IncomingVisited, Depth + 1);
      if (!IncomingVar.Base)
        continue;

      Value *IncomingBase = normalizeVariable(IncomingVar.Base);
      if (!HasIncoming) {
        Merged.Base = IncomingBase;
        appendOffsets(Merged.Offsets, IncomingVar.Offsets);
        Merged.HasStaticByteOffset = IncomingVar.HasStaticByteOffset;
        Merged.StaticByteOffset = IncomingVar.StaticByteOffset;
        HasIncoming = true;
      } else if (Merged.Base != IncomingBase ||
                 !sameOffsets(Merged.Offsets, IncomingVar.Offsets) ||
                 !sameRegionStart(Merged, IncomingVar)) {
        SameBase = false;
      }
    }

    if (HasIncoming && SameBase)
      return Merged;

    Result.Base = Phi;
    return Result;
  }

  if (auto *Select = dyn_cast<SelectInst>(V)) {
    SmallPtrSet<Value *, 16> TrueVisited = cloneVisited(Visited);
    SmallPtrSet<Value *, 16> FalseVisited = cloneVisited(Visited);
    CheckedVariable TrueVar =
        traceCheckedValueImpl(Select->getTrueValue(), TrueVisited, Depth + 1);
    CheckedVariable FalseVar =
        traceCheckedValueImpl(Select->getFalseValue(), FalseVisited,
                              Depth + 1);

    Value *TrueBase = normalizeVariable(TrueVar.Base);
    Value *FalseBase = normalizeVariable(FalseVar.Base);
    if (TrueBase && TrueBase == FalseBase) {
      if (!sameOffsets(TrueVar.Offsets, FalseVar.Offsets) ||
          !sameRegionStart(TrueVar, FalseVar)) {
        Result.Base = Select;
        return Result;
      }
      Result.Base = TrueBase;
      appendOffsets(Result.Offsets, TrueVar.Offsets);
      Result.HasStaticByteOffset = TrueVar.HasStaticByteOffset;
      Result.StaticByteOffset = TrueVar.StaticByteOffset;
      return Result;
    }

    Result.Base = Select;
    return Result;
  }

  if (auto *Cmp = dyn_cast<CmpInst>(V)) {
    Value *Operand = firstNonConstant(Cmp->getOperand(0), Cmp->getOperand(1));
    return traceCheckedValueImpl(Operand, Visited, Depth + 1);
  }

  if (auto *BinOp = dyn_cast<BinaryOperator>(V)) {
    Value *PointerOperand = recoverAddressPointer(BinOp->getOperand(0));
    Value *OffsetOperand = BinOp->getOperand(1);
    if (!PointerOperand) {
      PointerOperand = recoverAddressPointer(BinOp->getOperand(1));
      OffsetOperand = BinOp->getOperand(0);
    }
    if (PointerOperand) {
      Result = traceCheckedValueImpl(PointerOperand, Visited, Depth + 1);
      appendOffset(Result.Offsets, OffsetOperand);
      markUnknownStaticOffset(Result);
      return Result;
    }

    Value *Operand =
        firstNonConstant(BinOp->getOperand(0), BinOp->getOperand(1));
    Result = traceCheckedValueImpl(Operand, Visited, Depth + 1);
    if (BinOp->getOpcode() == Instruction::Add ||
        BinOp->getOpcode() == Instruction::Sub) {
      Value *LHS = BinOp->getOperand(0);
      Value *RHS = BinOp->getOperand(1);
      Value *ConstantSide = isa<Constant>(LHS) ? LHS : RHS;
      if (auto *CI = dyn_cast<ConstantInt>(ConstantSide)) {
        appendOffset(Result.Offsets, ConstantSide);
        if (BinOp->getOpcode() == Instruction::Sub && ConstantSide == LHS)
          markUnknownStaticOffset(Result);
        else
          addStaticOffset(Result, BinOp->getOpcode() == Instruction::Sub
                                      ? -CI->getSExtValue()
                                      : CI->getSExtValue());
      } else if (isa<Constant>(ConstantSide)) {
        appendOffset(Result.Offsets, ConstantSide);
        markUnknownStaticOffset(Result);
      }
    }
    return Result;
  }

  return makeBaseVariable(normalizeVariable(V));
}

Value *CheckedVariableAnalyzer::normalizeVariableImpl(
    Value *V, SmallPtrSetImpl<Value *> &Visited, unsigned Depth) {
  if (!V)
    return nullptr;

  if (Depth > MaxTraceDepth || !Visited.insert(V).second)
    return V;

  V = V->stripPointerCasts();

  if (auto *GEP = dyn_cast<GetElementPtrInst>(V))
    return normalizeVariableImpl(GEP->getPointerOperand(), Visited, Depth + 1);

  if (auto *GEP = dyn_cast<GEPOperator>(V))
    return normalizeVariableImpl(GEP->getPointerOperand(), Visited, Depth + 1);

  if (auto *Cast = dyn_cast<CastInst>(V))
    return normalizeVariableImpl(Cast->getOperand(0), Visited, Depth + 1);

  if (auto *Cast = dyn_cast<ConstantExpr>(V))
    if (Cast->isCast())
      return normalizeVariableImpl(Cast->getOperand(0), Visited, Depth + 1);

  if (auto *Load = dyn_cast<LoadInst>(V))
    return normalizeVariableImpl(Load->getPointerOperand(), Visited,
                                 Depth + 1);

  if (auto *Store = dyn_cast<StoreInst>(V))
    return normalizeVariableImpl(Store->getPointerOperand(), Visited,
                                 Depth + 1);

  if (auto *Phi = dyn_cast<PHINode>(V)) {
    Value *CommonBase = nullptr;
    for (Value *Incoming : Phi->incoming_values()) {
      Value *IncomingBase = normalizeVariableImpl(Incoming, Visited, Depth + 1);
      if (!IncomingBase)
        continue;
      if (!CommonBase)
        CommonBase = IncomingBase;
      else if (CommonBase != IncomingBase)
        return Phi;
    }
    return CommonBase ? CommonBase : Phi;
  }

  if (auto *Select = dyn_cast<SelectInst>(V)) {
    Value *TrueBase =
        normalizeVariableImpl(Select->getTrueValue(), Visited, Depth + 1);
    Value *FalseBase =
        normalizeVariableImpl(Select->getFalseValue(), Visited, Depth + 1);
    if (TrueBase && TrueBase == FalseBase)
      return TrueBase;
    return Select;
  }

  if (auto *BinOp = dyn_cast<BinaryOperator>(V)) {
    Value *Operand =
        firstNonConstant(BinOp->getOperand(0), BinOp->getOperand(1));
    return normalizeVariableImpl(Operand, Visited, Depth + 1);
  }

  return V;
}

AccessType CheckedVariableAnalyzer::inferAccessTypeFromUses(
    Value *CheckedValue, CallBase *CheckInst) {
  if (!CheckedValue)
    return AccessType::UNKNOWN;

  bool SawRead = false;
  bool SawWrite = false;
  SmallVector<Value *, 16> Worklist;
  SmallPtrSet<Value *, 32> Visited;
  Worklist.push_back(CheckedValue);

  for (unsigned Depth = 0; !Worklist.empty() && Depth < MaxUseTraceDepth;
       ++Depth) {
    SmallVector<Value *, 16> NextWorklist;
    for (Value *Current : Worklist) {
      if (!Current || !Visited.insert(Current).second)
        continue;

      for (User *U : Current->users()) {
        if (CheckInst)
          if (auto *UserI = dyn_cast<Instruction>(U))
            if (UserI->getFunction() != CheckInst->getFunction())
              continue;

        if (U == CheckInst)
          continue;

        if (auto *Load = dyn_cast<LoadInst>(U)) {
          if (normalizeVariable(Load->getPointerOperand()) ==
              normalizeVariable(Current))
            SawRead = true;
        } else if (auto *Store = dyn_cast<StoreInst>(U)) {
          if (normalizeVariable(Store->getPointerOperand()) ==
              normalizeVariable(Current))
            SawWrite = true;
        } else if (Value *Dest = getMemIntrinsicDest(U)) {
          if (normalizeVariable(Dest) == normalizeVariable(Current))
            SawWrite = true;
          if (Value *Src = getMemIntrinsicSource(U))
            if (normalizeVariable(Src) == normalizeVariable(Current))
              SawRead = true;
        } else if (isTraceThroughInstruction(U)) {
          NextWorklist.push_back(U);
        }
      }
    }
    Worklist.swap(NextWorklist);
  }

  if (SawRead && !SawWrite)
    return AccessType::READ;
  if (SawWrite && !SawRead)
    return AccessType::WRITE;
  return AccessType::UNKNOWN;
}

void printCheckedVariable(raw_ostream &OS, const CheckedVariable &Variable) {
  OS << "Sanitizer: " << sanitizerKindName(Variable.Sanitizer) << "\n";
  OS << "Access Type: " << accessTypeName(Variable.Type) << "\n";
  OS << "Base: ";
  if (Variable.Base)
    Variable.Base->printAsOperand(OS, false);
  else
    OS << "<unknown>";
  OS << "\n";

  OS << "Address: ";
  if (Variable.Address)
    Variable.Address->printAsOperand(OS, false);
  else
    OS << "<unknown>";
  OS << "\n";

  OS << "Offsets:";
  if (Variable.Offsets.empty()) {
    OS << " <none>\n";
  } else {
    for (Value *Offset : Variable.Offsets) {
      OS << " ";
      if (Offset)
        Offset->printAsOperand(OS, false);
      else
        OS << "<null>";
    }
    OS << "\n";
  }

  OS << "Region: ";
  if (Variable.HasStaticByteOffset)
    OS << "static-offset=" << Variable.StaticByteOffset;
  else
    OS << "static-offset=<unknown>";

  OS << ", access-size=";
  if (Variable.AccessSize != 0)
    OS << Variable.AccessSize;
  else
    OS << "<unknown>";
  OS << "\n";
}

} // namespace desan
