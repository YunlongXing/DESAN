#ifndef DESAN_REDUNDANT_CHECK_ELIMINATOR_H
#define DESAN_REDUNDANT_CHECK_ELIMINATOR_H

#include "DESAN/CheckGraphBuilder.h"
#include "DESAN/CheckSliceRemover.h"

#include "llvm/ADT/ArrayRef.h"
#include "llvm/ADT/SmallPtrSet.h"
#include "llvm/ADT/SmallVector.h"
#include "llvm/Support/raw_ostream.h"

#include <cstddef>
#include <string>

namespace llvm {
class CallBase;
class Module;
} // namespace llvm

namespace desan {

class RedundantCheckEliminator {
public:
  using CheckStat = SanitizerCheckCollector::CheckStat;

  RedundantCheckEliminator(llvm::Module &M,
                           llvm::ArrayRef<CheckStat> CoreChecks);

  std::size_t eliminateRedundantChecks();

  std::size_t eraseMarkedChecks();

  void dumpRemovalCandidates(llvm::raw_ostream &OS) const;

private:
  struct RemovalCandidate {
    std::string CheckText;
    CheckedVariable Var;
    AccessType Type = AccessType::UNKNOWN;
    SanitizerKind Sanitizer = SanitizerKind::Unknown;
    std::string BasicBlockName;
  };

  void markForRemoval(const CheckedVariable &Var, AccessType Type);

  CheckGraphBuilder GraphBuilder;
  CheckSliceRemover SliceRemover;
  llvm::SmallPtrSet<llvm::CallBase *, 32> MarkedCalls;
  llvm::SmallVector<RemovalCandidate, 32> RemovalCandidates;
};

} // namespace desan

#endif // DESAN_REDUNDANT_CHECK_ELIMINATOR_H
