#include "DESAN/CheckGraphBuilder.h"
#include "DESAN/CheckedVariableAnalyzer.h"
#include "DESAN/LLMAssistedAnalyzer.h"
#include "DESAN/RedundantCheckEliminator.h"
#include "DESAN/SanitizerCheckCollector.h"

#include "llvm/ADT/SmallVector.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/Module.h"
#include "llvm/IR/PassManager.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Passes/PassPlugin.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/Format.h"
#include "llvm/Support/raw_ostream.h"

#include <memory>
#include <optional>
#include <set>
#include <string>
#include <utility>

using namespace llvm;

namespace {

using CoreCheckKey = std::pair<desan::SanitizerKind, std::string>;

cl::opt<unsigned>
    CoreTopN("desan-core-top-n", cl::init(4), cl::Hidden,
             cl::desc("Maximum number of core sanitizer check types to report "
                      "per sanitizer. 0 means unlimited."));

cl::opt<double> CoreMinRatio(
    "desan-core-min-ratio", cl::init(5.0), cl::Hidden,
    cl::desc("Minimum within-sanitizer count ratio for a check type to be "
             "reported as core after the first check type."));

cl::opt<std::string>
    ProfileFile("desan-profile-file", cl::init(""), cl::Hidden,
                cl::desc("Optional CSV/TSV profile file. Supported rows: "
                         "'check_type,cost' or 'sanitizer,check_type,cost'."));

cl::opt<bool> DumpCheckedVariables(
    "desan-dump-checked-vars", cl::init(false), cl::Hidden,
    cl::desc("Dump checked variable tracing results for identified core "
             "sanitizer checks."));

cl::opt<bool> DumpCheckGraphs(
    "desan-dump-check-graphs", cl::init(false), cl::Hidden,
    cl::desc("Dump per-variable sanitizer check CFG graphs."));

cl::opt<bool> EliminateRedundantReads(
    "desan-eliminate-redundant-reads", cl::init(true), cl::Hidden,
    cl::desc("Remove redundant sanitizer READ checks using the current "
             "per-variable retention policy."));

cl::opt<bool> DumpRemovals(
    "desan-dump-removals", cl::init(false), cl::Hidden,
    cl::desc("Dump redundant READ checks selected for removal."));

cl::opt<bool> EnableLLMAssist(
    "desan-enable-llm-assist", cl::init(false), cl::Hidden,
    cl::desc("Enable optional LLM-assisted sanitizer check explanations. "
             "LLM output is advisory only and never decides deletion."));

cl::opt<std::string> LLMCommand(
    "desan-llm-command", cl::init(""), cl::Hidden,
    cl::desc("Optional command used for LLM assistance. The command receives "
             "the prompt on stdin and should write JSON to stdout."));

cl::opt<unsigned> LLMMaxQueries(
    "desan-llm-max-queries", cl::init(8), cl::Hidden,
    cl::desc("Maximum number of LLM advisory queries to emit. 0 means "
             "unlimited."));

cl::opt<unsigned> LLMMaxSliceInstructions(
    "desan-llm-max-slice-insts", cl::init(32), cl::Hidden,
    cl::desc("Maximum number of backward-slice instructions included in each "
             "LLM prompt."));

cl::opt<bool> LLMDumpPrompts(
    "desan-llm-dump-prompts", cl::init(true), cl::Hidden,
    cl::desc("Dump LLM prompts in DESAN logs."));

cl::opt<bool> LLMOnlyUncertain(
    "desan-llm-only-uncertain", cl::init(true), cl::Hidden,
    cl::desc("Emit LLM advisory queries only for UNKNOWN or ambiguous "
             "checked-variable cases."));

bool hasAmbiguousValue(const desan::CheckedVariable &Var) {
  if (!Var.Base)
    return true;
  if (isa<PHINode>(Var.Base) || isa<SelectInst>(Var.Base))
    return true;
  for (Value *Offset : Var.Offsets) {
    if (!Offset)
      return true;
    if (isa<PHINode>(Offset) || isa<SelectInst>(Offset))
      return true;
  }
  return false;
}

bool shouldAskLLMAboutVariable(const desan::CheckedVariable &Var) {
  if (!LLMOnlyUncertain)
    return true;
  return Var.Type == desan::AccessType::UNKNOWN || hasAmbiguousValue(Var);
}

bool canIssueLLMQuery(unsigned QueryCount) {
  return LLMMaxQueries == 0 || QueryCount < LLMMaxQueries;
}

void runLLMAssistedAnalysis(
    Module &M, ArrayRef<desan::SanitizerCheckCollector::CheckStat> CoreChecks,
    const std::set<CoreCheckKey> &CoreCheckSet,
    const desan::SanitizerCheckCollector &Collector) {
  desan::LLMAssistedAnalyzer LLM(LLMCommand, LLMMaxSliceInstructions);
  desan::CheckedVariableAnalyzer Analyzer;

  errs() << "DESAN LLM-Assisted Analysis\n";
  errs() << "Mode: "
         << (LLMCommand.empty() ? "prompt/log only" : "external command")
         << "\n";
  errs() << "Safety: advisory only; static analysis remains the only deletion "
            "authority.\n";

  unsigned Queries = 0;
  SmallVector<desan::CheckedVariable, 8> RecentVariables;

  for (Function &F : M) {
    if (!canIssueLLMQuery(Queries))
      break;
    if (F.isDeclaration())
      continue;

    for (Instruction &I : instructions(F)) {
      if (!canIssueLLMQuery(Queries))
        break;

      auto *CB = dyn_cast<CallBase>(&I);
      if (!CB)
        continue;

      std::optional<desan::SanitizerCheckCollector::ClassifiedCheck> Check =
          Collector.classifyCheck(CB);
      if (!Check)
        continue;

      if (!CoreCheckSet.empty() &&
          !CoreCheckSet.count({Check->Sanitizer, Check->CheckType}))
        continue;

      std::optional<desan::CheckedVariable> Variable =
          Analyzer.analyzeCheck(CB);
      if (!Variable)
        continue;

      if (shouldAskLLMAboutVariable(*Variable)) {
        desan::LLMQueryResult Result = LLM.askIfCheckIsReadOrWrite(CB);
        LLM.dumpResult(errs(), "checked variable and access type", Result,
                       LLMDumpPrompts);
        ++Queries;
      }

      if (canIssueLLMQuery(Queries) && !RecentVariables.empty() &&
          (shouldAskLLMAboutVariable(*Variable) ||
           shouldAskLLMAboutVariable(RecentVariables.back()))) {
        desan::LLMQueryResult Result =
            LLM.askIfSameCheckedVariable(RecentVariables.back(), *Variable);
        LLM.dumpResult(errs(), "same checked variable", Result,
                       LLMDumpPrompts);
        ++Queries;
      }

      RecentVariables.push_back(*Variable);
      if (RecentVariables.size() > 4)
        RecentVariables.erase(RecentVariables.begin());
    }
  }

  if (canIssueLLMQuery(Queries)) {
    desan::CheckGraphBuilder GraphBuilder(M, CoreChecks);
    const desan::CheckGraphBuilder::VariableCheckGroups &Groups =
        GraphBuilder.groupChecksByVariable();

    for (const auto &Group : Groups) {
      if (!canIssueLLMQuery(Queries))
        break;
      if (Group.second.empty())
        continue;

      std::unique_ptr<desan::CheckGraph> Graph =
          GraphBuilder.buildGraphForVariable(Group.second.front());
      for (desan::CheckNode *Node : Graph->Nodes) {
        if (!canIssueLLMQuery(Queries))
          break;
        if (!Node || !Node->CheckInst)
          continue;
        if (Node->Type != desan::AccessType::READ &&
            Node->Type != desan::AccessType::UNKNOWN)
          continue;

        bool StaticPolicyMayRemove = Node->Type == desan::AccessType::READ;
        if (LLMOnlyUncertain && StaticPolicyMayRemove &&
            !hasAmbiguousValue(Node->Var))
          continue;

        desan::LLMQueryResult Result =
            LLM.askIfSafeToRemove(Node, StaticPolicyMayRemove);
        LLM.dumpResult(errs(), "safe-to-remove explanation", Result,
                       LLMDumpPrompts);
        ++Queries;
      }
    }
  }

  errs() << "DESAN LLM Assist Queries: " << Queries << "\n";
}

class SanitizerCheckCollectorPass
    : public PassInfoMixin<SanitizerCheckCollectorPass> {
public:
  PreservedAnalyses run(Module &M, ModuleAnalysisManager &) {
    desan::SanitizerCheckCollector Collector;
    if (!ProfileFile.empty())
      Collector.loadProfile(ProfileFile, &errs());

    for (Function &F : M) {
      if (!F.isDeclaration())
        Collector.collectChecks(F);
    }

    Collector.dumpCheckStatistics(errs());

    SmallVector<desan::SanitizerCheckCollector::CheckStat, 16> CoreChecks =
        Collector.identifyCoreChecks(CoreTopN, CoreMinRatio);
    std::set<CoreCheckKey> CoreCheckSet;

    errs() << "DESAN Core Check Summary\n";
    for (const auto &Stat : CoreChecks) {
      CoreCheckSet.insert({Stat.Sanitizer, Stat.CheckType});
      errs() << desan::sanitizerKindName(Stat.Sanitizer) << " "
             << Stat.CheckType << " count=" << Stat.Count
             << " ratio=" << format("%.1f%%", Stat.RatioWithinSanitizer);
      if (Stat.RuntimeRatio >= 0.0)
        errs() << " runtime=" << format("%.1f%%", Stat.RuntimeRatio);
      errs() << "\n";
    }

    if (DumpCheckedVariables) {
      desan::CheckedVariableAnalyzer Analyzer;
      errs() << "DESAN Checked Variables\n";

      for (Function &F : M) {
        if (F.isDeclaration())
          continue;

        for (Instruction &I : instructions(F)) {
          auto *CB = dyn_cast<CallBase>(&I);
          if (!CB)
            continue;

          std::optional<desan::SanitizerCheckCollector::ClassifiedCheck>
              Check = Collector.classifyCheck(CB);
          if (!Check)
            continue;

          if (!CoreCheckSet.empty() &&
              !CoreCheckSet.count({Check->Sanitizer, Check->CheckType}))
            continue;

          std::optional<desan::CheckedVariable> Variable =
              Analyzer.analyzeCheck(CB);
          if (!Variable)
            continue;

          errs() << "Function: " << F.getName() << "\n";
          errs() << "Check Type: " << Check->CheckType << "\n";
          desan::printCheckedVariable(errs(), *Variable);
          errs() << "\n";
        }
      }
    }

    if (EnableLLMAssist)
      runLLMAssistedAnalysis(M, CoreChecks, CoreCheckSet, Collector);

    if (DumpCheckGraphs) {
      desan::CheckGraphBuilder GraphBuilder(M, CoreChecks);
      const desan::CheckGraphBuilder::VariableCheckGroups &Groups =
          GraphBuilder.groupChecksByVariable();

      errs() << "DESAN Per-Variable Check Graphs\n";
      for (const auto &Group : Groups) {
        if (Group.second.empty())
          continue;

        std::unique_ptr<desan::CheckGraph> Graph =
            GraphBuilder.buildGraphForVariable(Group.second.front());
        desan::printCheckGraph(errs(), *Graph);
        errs() << "\n";
      }
    }

    std::size_t RemovedCount = 0;
    if (EliminateRedundantReads) {
      desan::RedundantCheckEliminator Eliminator(M, CoreChecks);
      RemovedCount = Eliminator.eliminateRedundantChecks();
      if (DumpRemovals)
        Eliminator.dumpRemovalCandidates(errs());
      errs() << "DESAN Removed Redundant Checks: " << RemovedCount
             << "\n";
    }

    return RemovedCount == 0 ? PreservedAnalyses::all()
                             : PreservedAnalyses::none();
  }
};

} // namespace

extern "C" LLVM_ATTRIBUTE_WEAK PassPluginLibraryInfo llvmGetPassPluginInfo() {
  return {LLVM_PLUGIN_API_VERSION, "DESANPass", LLVM_VERSION_STRING,
          [](PassBuilder &PB) {
            PB.registerPipelineParsingCallback(
                [](StringRef Name, ModulePassManager &MPM,
                   ArrayRef<PassBuilder::PipelineElement>) {
                  if (Name == "desan-collect-checks") {
                    MPM.addPass(SanitizerCheckCollectorPass());
                    return true;
                  }
                  return false;
                });
          }};
}
