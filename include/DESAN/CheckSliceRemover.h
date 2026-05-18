#ifndef DESAN_CHECK_SLICE_REMOVER_H
#define DESAN_CHECK_SLICE_REMOVER_H

#include "DESAN/CheckGraphBuilder.h"
#include "DESAN/SanitizerCheckCollector.h"

#include "llvm/ADT/SmallPtrSet.h"
#include "llvm/ADT/SmallVector.h"
#include "llvm/IR/BasicBlock.h"
#include "llvm/IR/InstrTypes.h"
#include "llvm/IR/Instruction.h"

#include <cstddef>

namespace llvm {
class Function;
class Module;
class Value;
} // namespace llvm

namespace desan {

struct CheckSlice {
  llvm::SmallPtrSet<llvm::Instruction *, 32> Instructions;
  llvm::SmallVector<llvm::Instruction *, 32> OrderedInstructions;
  llvm::SmallPtrSet<llvm::BasicBlock *, 8> Blocks;
  llvm::SmallVector<llvm::BasicBlock *, 8> OrderedBlocks;
};

class CheckSliceRemover {
public:
  explicit CheckSliceRemover(llvm::Module &M);

  CheckSlice collectCheckSlice(llvm::CallBase *CB);

  bool isSanitizerOnlyInstruction(llvm::Instruction *I) const;

  bool removeCheckSlice(CheckNode *N);

  std::size_t cleanupDeadInstructions();

  bool simplifyCFG();

private:
  bool addInstruction(CheckSlice &Slice, llvm::Instruction *I);

  bool addBlock(CheckSlice &Slice, llvm::BasicBlock *BB);

  void collectBackwardFromInstruction(CheckSlice &Slice, llvm::Instruction *I);

  void collectBackwardFromValue(CheckSlice &Slice, llvm::Value *V,
                                llvm::Function *F);

  void collectControlFlowSlice(CheckSlice &Slice, llvm::CallBase *CB);

  bool isSanitizerOnlyBlock(llvm::BasicBlock *BB,
                            llvm::CallBase *TargetCB = nullptr) const;

  bool canEraseInstruction(llvm::Instruction *I, const CheckSlice &Slice) const;

  bool allUsersInsideSlice(llvm::Instruction *I,
                           const CheckSlice &Slice) const;

  bool bypassReportBlock(CheckSlice &Slice, llvm::CallBase *CB);

  bool eraseDirectCheckCall(llvm::CallBase *CB);

  std::size_t eraseDeadSliceInstructions(CheckSlice &Slice);

  llvm::Module &M;
  SanitizerCheckCollector Collector;
  llvm::SmallPtrSet<llvm::Function *, 8> TouchedFunctions;
};

} // namespace desan

#endif // DESAN_CHECK_SLICE_REMOVER_H
