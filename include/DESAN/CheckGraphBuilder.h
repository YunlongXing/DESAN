#ifndef DESAN_CHECK_GRAPH_BUILDER_H
#define DESAN_CHECK_GRAPH_BUILDER_H

#include "DESAN/CheckedVariableAnalyzer.h"

#include "llvm/ADT/ArrayRef.h"
#include "llvm/ADT/SmallVector.h"
#include "llvm/IR/BasicBlock.h"
#include "llvm/IR/InstrTypes.h"
#include "llvm/IR/Value.h"
#include "llvm/Support/raw_ostream.h"

#include <map>
#include <memory>
#include <cstdint>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace llvm {
class DominatorTree;
class Function;
class Module;
} // namespace llvm

namespace desan {

struct VariableKey {
  SanitizerKind Sanitizer = SanitizerKind::Unknown;
  llvm::Value *Base = nullptr;
  llvm::SmallVector<llvm::Value *, 4> Offsets;
  bool HasStaticByteOffset = false;
  int64_t StaticByteOffset = 0;
};

struct VariableKeyLess {
  bool operator()(const VariableKey &LHS, const VariableKey &RHS) const;
};

struct CheckNode {
  unsigned Id = 0;
  llvm::CallBase *CheckInst = nullptr;
  llvm::Instruction *AnchorInst = nullptr;
  CheckedVariable Var;
  AccessType Type = AccessType::UNKNOWN;
  llvm::BasicBlock *BB = nullptr;
  llvm::SmallVector<CheckNode *, 4> Successors;
  llvm::SmallVector<CheckNode *, 4> Predecessors;
  llvm::SmallVector<CheckNode *, 4> Dominators;
  llvm::SmallVector<CheckNode *, 4> DominatedNodes;
};

struct CheckGraph {
  CheckedVariable Var;
  VariableKey Key;
  std::vector<std::unique_ptr<CheckNode>> OwnedNodes;
  llvm::SmallVector<CheckNode *, 8> Nodes;
};

class CheckGraphBuilder {
public:
  using CheckStat = SanitizerCheckCollector::CheckStat;
  using CoreCheckKey = std::pair<SanitizerKind, std::string>;
  using VariableCheckGroups =
      std::map<VariableKey, llvm::SmallVector<CheckedVariable, 8>,
               VariableKeyLess>;

  CheckGraphBuilder(llvm::Module &M, llvm::ArrayRef<CheckStat> CoreChecks);
  ~CheckGraphBuilder();

  const VariableCheckGroups &groupChecksByVariable();

  std::unique_ptr<CheckGraph> buildGraphForVariable(CheckedVariable Var);

  void computeReachability(CheckGraph &Graph);

  void computeDominance(CheckGraph &Graph);

private:
  VariableKey makeVariableKey(const CheckedVariable &Var) const;

  bool isCoreCheck(const SanitizerCheckCollector::ClassifiedCheck &Check) const;

  bool isReachable(const CheckNode &From, const CheckNode &To) const;

  llvm::DominatorTree &getDominatorTree(llvm::Function &F);

  llvm::Module &M;
  std::set<CoreCheckKey> CoreCheckSet;
  CheckedVariableAnalyzer Analyzer;
  SanitizerCheckCollector Collector;
  VariableCheckGroups Groups;
  std::map<llvm::Function *, std::unique_ptr<llvm::DominatorTree>>
      DominatorTrees;
  bool GroupsComputed = false;
};

void printVariableKey(llvm::raw_ostream &OS, const VariableKey &Key);

void printCheckGraph(llvm::raw_ostream &OS, const CheckGraph &Graph);

} // namespace desan

#endif // DESAN_CHECK_GRAPH_BUILDER_H
