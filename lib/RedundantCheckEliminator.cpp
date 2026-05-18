#include "DESAN/RedundantCheckEliminator.h"

#include "llvm/IR/BasicBlock.h"
#include "llvm/IR/InstrTypes.h"
#include "llvm/IR/Module.h"
#include "llvm/Support/raw_ostream.h"

#include <string>
#include <utility>

using namespace llvm;

namespace desan {

namespace {

// Per-variable retention policy: keep the first check, keep every WRITE,
// keep the first READ after a WRITE/UNKNOWN barrier, and remove other READs.
class ReadRetentionState {
public:
  bool shouldKeep(AccessType Type) {
    if (Type == AccessType::UNKNOWN) {
      KeepNextRead = true;
      return true;
    }

    if (Type == AccessType::WRITE) {
      SeenAnyCheck = true;
      KeepNextRead = true;
      return true;
    }

    if (Type != AccessType::READ)
      return true;

    if (!SeenAnyCheck) {
      SeenAnyCheck = true;
      KeepNextRead = false;
      return true;
    }

    if (KeepNextRead) {
      KeepNextRead = false;
      return true;
    }

    return false;
  }

private:
  bool SeenAnyCheck = false;
  bool KeepNextRead = false;
};

} // namespace

RedundantCheckEliminator::RedundantCheckEliminator(
    Module &M, ArrayRef<CheckStat> CoreChecks)
    : GraphBuilder(M, CoreChecks), SliceRemover(M) {}

void RedundantCheckEliminator::markForRemoval(const CheckedVariable &Var,
                                              AccessType Type) {
  if (!Var.CheckInst)
    return;
  if (!MarkedCalls.insert(Var.CheckInst).second)
    return;

  RemovalCandidate Candidate;
  std::string CheckText;
  raw_string_ostream CheckOS(CheckText);
  Var.CheckInst->print(CheckOS);
  Candidate.CheckText = CheckOS.str();
  Candidate.Var = Var;
  Candidate.Var.CheckInst = nullptr;
  Candidate.Var.Address = nullptr;
  Candidate.Type = Type;
  Candidate.Sanitizer = Var.Sanitizer;

  BasicBlock *BB = Var.CheckInst->getParent();
  if (BB && BB->hasName())
    Candidate.BasicBlockName = BB->getName().str();
  else if (BB)
    Candidate.BasicBlockName = "<unnamed>";
  else
    Candidate.BasicBlockName = "<unknown>";

  RemovalCandidates.push_back(std::move(Candidate));
}

std::size_t RedundantCheckEliminator::eliminateRedundantChecks() {
  const CheckGraphBuilder::VariableCheckGroups &Groups =
      GraphBuilder.groupChecksByVariable();

  for (const auto &Group : Groups) {
    if (Group.second.empty())
      continue;

    ReadRetentionState Retention;
    for (const CheckedVariable &Var : Group.second) {
      if (!Var.CheckInst)
        continue;
      if (Retention.shouldKeep(Var.Type))
        continue;
      if (Var.Type == AccessType::READ)
        markForRemoval(Var, Var.Type);
    }
  }

  return eraseMarkedChecks();
}

std::size_t RedundantCheckEliminator::eraseMarkedChecks() {
  SmallVector<CallBase *, 32> CallsToErase;
  for (CallBase *CB : MarkedCalls) {
    if (CB)
      CallsToErase.push_back(CB);
  }

  std::size_t Removed = 0;
  for (CallBase *CB : CallsToErase) {
    CheckNode Node;
    Node.CheckInst = CB;
    Node.BB = CB->getParent();
    if (SliceRemover.removeCheckSlice(&Node))
      ++Removed;
  }

  SliceRemover.cleanupDeadInstructions();
  SliceRemover.simplifyCFG();
  return Removed;
}

void RedundantCheckEliminator::dumpRemovalCandidates(raw_ostream &OS) const {
  OS << "DESAN Redundant Read Check Candidates\n";
  if (RemovalCandidates.empty()) {
    OS << "None\n";
    return;
  }

  for (const RemovalCandidate &Candidate : RemovalCandidates) {
    OS << "Check: " << Candidate.CheckText << "\n";
    OS << "Sanitizer: " << sanitizerKindName(Candidate.Sanitizer) << "\n";
    OS << "Access Type: " << accessTypeName(Candidate.Type) << "\n";
    OS << "BasicBlock: " << Candidate.BasicBlockName << "\n";
    printCheckedVariable(OS, Candidate.Var);
    OS << "\n";
  }
}

} // namespace desan
