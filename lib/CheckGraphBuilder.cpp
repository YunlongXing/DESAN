#include "DESAN/CheckGraphBuilder.h"

#include "llvm/ADT/STLExtras.h"
#include "llvm/ADT/SmallPtrSet.h"
#include "llvm/IR/CFG.h"
#include "llvm/IR/Dominators.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/Module.h"
#include "llvm/Support/CommandLine.h"

#include <cstdint>
#include <iterator>
#include <queue>

using namespace llvm;

namespace desan {

namespace {

cl::opt<bool> GroupDynamicOffsetsByBase(
    "desan-group-dynamic-offsets", cl::init(true), cl::Hidden,
    cl::desc("Group non-constant GEP/index expressions by normalized base "
             "instead of exact SSA offset identity. This increases ASan "
             "array/loop READ coalescing under the first-read policy."));

cl::opt<bool> DistinguishStaticOffsets(
    "desan-distinguish-static-offsets", cl::init(false), cl::Hidden,
    cl::desc("Include exact static byte offsets in checked-variable keys. "
             "Disabled by default to preserve the current aggressive "
             "base-level elimination policy."));

uintptr_t valueAddress(Value *V) {
  return reinterpret_cast<uintptr_t>(V);
}

void appendUniqueNode(SmallVectorImpl<CheckNode *> &Nodes, CheckNode *Node) {
  if (!Node || is_contained(Nodes, Node))
    return;
  Nodes.push_back(Node);
}

bool instructionComesBefore(const Instruction *From, const Instruction *To) {
  if (!From || !To || From->getParent() != To->getParent())
    return false;

  const BasicBlock *BB = From->getParent();
  for (auto It = std::next(From->getIterator()), End = BB->end(); It != End;
       ++It) {
    if (&*It == To)
      return true;
  }
  return false;
}

bool isASanReportCall(const CallBase *CB) {
  if (!CB || !CB->getCalledFunction())
    return false;

  StringRef Name = CB->getCalledFunction()->getName();
  return Name.starts_with("__asan_report_load") ||
         Name.starts_with("__asan_report_store") ||
         Name.starts_with("__asan_report_exp_load") ||
         Name.starts_with("__asan_report_exp_store") ||
         Name.starts_with("__asan_report_error");
}

bool isMemSanReportCall(const CallBase *CB) {
  if (!CB || !CB->getCalledFunction())
    return false;

  StringRef Name = CB->getCalledFunction()->getName();
  Name.consume_front("\01");
  if (Name.starts_with("___msan_"))
    Name = Name.drop_front();
  return Name.starts_with("__msan_warning");
}

Instruction *findCheckAnchor(CallBase *CB) {
  if (!CB)
    return nullptr;

  if (!isASanReportCall(CB) && !isMemSanReportCall(CB))
    return CB;

  BasicBlock *ReportBB = CB->getParent();
  if (!ReportBB)
    return CB;

  Instruction *Anchor = nullptr;
  for (BasicBlock *Pred : predecessors(ReportBB)) {
    auto *BI = dyn_cast<BranchInst>(Pred->getTerminator());
    if (!BI || !BI->isConditional())
      return CB;

    bool BranchesToReport = false;
    for (unsigned I = 0, E = BI->getNumSuccessors(); I != E; ++I)
      BranchesToReport |= BI->getSuccessor(I) == ReportBB;
    if (!BranchesToReport)
      return CB;

    if (Anchor)
      return CB;
    Anchor = BI;
  }

  return Anchor ? Anchor : CB;
}

Instruction *nodeAnchor(const CheckNode &Node) {
  if (Node.AnchorInst)
    return Node.AnchorInst;
  return Node.CheckInst;
}

} // namespace

bool VariableKeyLess::operator()(const VariableKey &LHS,
                                 const VariableKey &RHS) const {
  if (LHS.Sanitizer != RHS.Sanitizer)
    return static_cast<unsigned>(LHS.Sanitizer) <
           static_cast<unsigned>(RHS.Sanitizer);

  if (valueAddress(LHS.Base) != valueAddress(RHS.Base))
    return valueAddress(LHS.Base) < valueAddress(RHS.Base);

  if (LHS.Offsets.size() != RHS.Offsets.size())
    return LHS.Offsets.size() < RHS.Offsets.size();

  for (auto [LHSOffset, RHSOffset] : zip(LHS.Offsets, RHS.Offsets)) {
    if (valueAddress(LHSOffset) != valueAddress(RHSOffset))
      return valueAddress(LHSOffset) < valueAddress(RHSOffset);
  }

  if (LHS.HasStaticByteOffset != RHS.HasStaticByteOffset)
    return LHS.HasStaticByteOffset < RHS.HasStaticByteOffset;

  if (LHS.HasStaticByteOffset &&
      LHS.StaticByteOffset != RHS.StaticByteOffset)
    return LHS.StaticByteOffset < RHS.StaticByteOffset;

  return false;
}

CheckGraphBuilder::CheckGraphBuilder(Module &M, ArrayRef<CheckStat> CoreChecks)
    : M(M) {
  for (const CheckStat &Stat : CoreChecks)
    CoreCheckSet.insert({Stat.Sanitizer, Stat.CheckType});
}

CheckGraphBuilder::~CheckGraphBuilder() = default;

const CheckGraphBuilder::VariableCheckGroups &
CheckGraphBuilder::groupChecksByVariable() {
  if (GroupsComputed)
    return Groups;

  Groups.clear();

  for (Function &F : M) {
    if (F.isDeclaration())
      continue;

    for (Instruction &I : instructions(F)) {
      auto *CB = dyn_cast<CallBase>(&I);
      if (!CB)
        continue;

      std::optional<SanitizerCheckCollector::ClassifiedCheck> Check =
          Collector.classifyCheck(CB);
      if (!Check || !isCoreCheck(*Check))
        continue;

      std::optional<CheckedVariable> Var = Analyzer.analyzeCheck(CB);
      if (!Var)
        continue;

      Groups[makeVariableKey(*Var)].push_back(*Var);
    }
  }

  GroupsComputed = true;
  return Groups;
}

std::unique_ptr<CheckGraph>
CheckGraphBuilder::buildGraphForVariable(CheckedVariable Var) {
  groupChecksByVariable();

  auto Graph = std::make_unique<CheckGraph>();
  Graph->Var = Var;
  Graph->Key = makeVariableKey(Var);

  auto GroupIt = Groups.find(Graph->Key);
  if (GroupIt == Groups.end())
    return Graph;

  for (const CheckedVariable &GroupedVar : GroupIt->second) {
    auto Node = std::make_unique<CheckNode>();
    Node->Id = Graph->Nodes.size();
    Node->CheckInst = GroupedVar.CheckInst;
    Node->AnchorInst = findCheckAnchor(GroupedVar.CheckInst);
    Node->Var = GroupedVar;
    Node->Type = GroupedVar.Type;
    Node->BB = Node->AnchorInst ? Node->AnchorInst->getParent()
                                : (GroupedVar.CheckInst
                                       ? GroupedVar.CheckInst->getParent()
                                       : nullptr);
    Graph->Nodes.push_back(Node.get());
    Graph->OwnedNodes.push_back(std::move(Node));
  }

  computeReachability(*Graph);
  computeDominance(*Graph);
  return Graph;
}

void CheckGraphBuilder::computeReachability(CheckGraph &Graph) {
  for (CheckNode *Node : Graph.Nodes) {
    Node->Successors.clear();
    Node->Predecessors.clear();
  }

  for (CheckNode *From : Graph.Nodes) {
    for (CheckNode *To : Graph.Nodes) {
      if (From == To)
        continue;

      if (!isReachable(*From, *To))
        continue;

      appendUniqueNode(From->Successors, To);
      appendUniqueNode(To->Predecessors, From);
    }
  }
}

void CheckGraphBuilder::computeDominance(CheckGraph &Graph) {
  for (CheckNode *Node : Graph.Nodes) {
    Node->Dominators.clear();
    Node->DominatedNodes.clear();
  }

  for (CheckNode *CandidateDom : Graph.Nodes) {
    Instruction *CandidateAnchor = nodeAnchor(*CandidateDom);
    if (!CandidateAnchor)
      continue;

    Function *DomFunction = CandidateAnchor->getFunction();
    DominatorTree &DT = getDominatorTree(*DomFunction);

    for (CheckNode *Node : Graph.Nodes) {
      Instruction *NodeAnchor = nodeAnchor(*Node);
      if (CandidateDom == Node || !NodeAnchor)
        continue;
      if (NodeAnchor->getFunction() != DomFunction)
        continue;

      if (!DT.dominates(CandidateAnchor, NodeAnchor))
        continue;

      appendUniqueNode(Node->Dominators, CandidateDom);
      appendUniqueNode(CandidateDom->DominatedNodes, Node);
    }
  }
}

VariableKey CheckGraphBuilder::makeVariableKey(const CheckedVariable &Var) const {
  VariableKey Key;
  Key.Sanitizer = Var.Sanitizer;
  Key.Base = Var.Base;

  if (DistinguishStaticOffsets && Var.HasStaticByteOffset) {
    Key.HasStaticByteOffset = true;
    Key.StaticByteOffset = Var.StaticByteOffset;
  }

  if (!Var.HasStaticByteOffset && !GroupDynamicOffsetsByBase)
    Key.Offsets.append(Var.Offsets.begin(), Var.Offsets.end());
  return Key;
}

bool CheckGraphBuilder::isCoreCheck(
    const SanitizerCheckCollector::ClassifiedCheck &Check) const {
  if (CoreCheckSet.empty())
    return true;
  return CoreCheckSet.count({Check.Sanitizer, Check.CheckType}) != 0;
}

bool CheckGraphBuilder::isReachable(const CheckNode &From,
                                    const CheckNode &To) const {
  Instruction *FromAnchor = nodeAnchor(From);
  Instruction *ToAnchor = nodeAnchor(To);

  if (!FromAnchor || !ToAnchor || !From.BB || !To.BB)
    return false;
  if (FromAnchor->getFunction() != ToAnchor->getFunction())
    return false;

  if (From.BB == To.BB)
    return instructionComesBefore(FromAnchor, ToAnchor);

  SmallPtrSet<const BasicBlock *, 32> Visited;
  std::queue<const BasicBlock *> Worklist;

  for (const BasicBlock *Succ : successors(From.BB))
    Worklist.push(Succ);

  while (!Worklist.empty()) {
    const BasicBlock *Current = Worklist.front();
    Worklist.pop();
    if (!Visited.insert(Current).second)
      continue;

    if (Current == To.BB)
      return true;

    for (const BasicBlock *Succ : successors(Current))
      Worklist.push(Succ);
  }

  return false;
}

DominatorTree &CheckGraphBuilder::getDominatorTree(Function &F) {
  auto It = DominatorTrees.find(&F);
  if (It != DominatorTrees.end())
    return *It->second;

  auto DT = std::make_unique<DominatorTree>(F);
  DominatorTree &Result = *DT;
  DominatorTrees[&F] = std::move(DT);
  return Result;
}

void printVariableKey(raw_ostream &OS, const VariableKey &Key) {
  OS << "Sanitizer: " << sanitizerKindName(Key.Sanitizer) << "\n";
  OS << "Base: ";
  if (Key.Base)
    Key.Base->printAsOperand(OS, false);
  else
    OS << "<unknown>";

  OS << "\nOffsets:";
  if (Key.Offsets.empty()) {
    OS << " <none>\n";
  } else {
    for (Value *Offset : Key.Offsets) {
      OS << " ";
      if (Offset)
        Offset->printAsOperand(OS, false);
      else
        OS << "<null>";
    }
    OS << "\n";
  }

  OS << "Region Start: ";
  if (Key.HasStaticByteOffset)
    OS << "static-offset=" << Key.StaticByteOffset << "\n";
  else
    OS << "static-offset=<unknown>\n";
}

void printCheckGraph(raw_ostream &OS, const CheckGraph &Graph) {
  OS << "Variable:\n";
  printVariableKey(OS, Graph.Key);
  OS << "Node Count: " << Graph.Nodes.size() << "\n";

  for (size_t Index = 0; Index < Graph.Nodes.size(); ++Index) {
    const CheckNode *Node = Graph.Nodes[Index];
    OS << "Node #" << Node->Id << "\n";
    OS << "  Check: ";
    if (Node->CheckInst)
      Node->CheckInst->print(OS);
    else
      OS << "<unknown>";
    OS << "\n";
    OS << "  Anchor: ";
    if (Node->AnchorInst)
      Node->AnchorInst->print(OS);
    else
      OS << "<unknown>";
    OS << "\n";
    OS << "  Sanitizer: " << sanitizerKindName(Node->Var.Sanitizer) << "\n";
    OS << "  Access Type: " << accessTypeName(Node->Type) << "\n";
    OS << "  BasicBlock: ";
    if (Node->BB && Node->BB->hasName())
      OS << Node->BB->getName();
    else if (Node->BB)
      OS << "<unnamed>";
    else
      OS << "<unknown>";
    OS << "\n";

    OS << "  Successors:";
    if (Node->Successors.empty())
      OS << " <none>";
    for (CheckNode *Succ : Node->Successors)
      OS << " #" << Succ->Id;
    OS << "\n";

    OS << "  Predecessors:";
    if (Node->Predecessors.empty())
      OS << " <none>";
    for (CheckNode *Pred : Node->Predecessors)
      OS << " #" << Pred->Id;
    OS << "\n";

    OS << "  Dominators:";
    if (Node->Dominators.empty())
      OS << " <none>";
    for (CheckNode *Dom : Node->Dominators)
      OS << " #" << Dom->Id;
    OS << "\n";

    OS << "  Dominated:";
    if (Node->DominatedNodes.empty())
      OS << " <none>";
    for (CheckNode *Dominated : Node->DominatedNodes)
      OS << " #" << Dominated->Id;
    OS << "\n";
  }
}

} // namespace desan
