#ifndef DESAN_LLM_ASSISTED_ANALYZER_H
#define DESAN_LLM_ASSISTED_ANALYZER_H

#include "DESAN/CheckGraphBuilder.h"

#include "llvm/ADT/StringRef.h"
#include "llvm/IR/InstrTypes.h"
#include "llvm/Support/raw_ostream.h"

#include <string>

namespace desan {

struct LLMQueryResult {
  std::string Prompt;
  std::string Response;
  std::string Error;
  int ExitCode = 0;
  bool Invoked = false;
  bool Succeeded = false;
};

class LLMAssistedAnalyzer {
public:
  explicit LLMAssistedAnalyzer(std::string Command = "",
                               unsigned MaxSliceInstructions = 32);

  std::string summarizeIRSlice(llvm::CallBase *CB) const;

  LLMQueryResult
  askIfSameCheckedVariable(const CheckedVariable &LHS,
                           const CheckedVariable &RHS) const;

  LLMQueryResult askIfCheckIsReadOrWrite(llvm::CallBase *CB) const;

  LLMQueryResult askIfSafeToRemove(const CheckNode *N,
                                   bool StaticPolicyCandidate) const;

  void dumpResult(llvm::raw_ostream &OS, llvm::StringRef Title,
                  const LLMQueryResult &Result,
                  bool IncludePrompt = true) const;

private:
  std::string buildCheckQuestion(llvm::CallBase *CB) const;

  std::string checkedVariableSummary(const CheckedVariable &Var) const;

  LLMQueryResult runPrompt(std::string Prompt) const;

  std::string Command;
  unsigned MaxSliceInstructions = 32;
};

} // namespace desan

#endif // DESAN_LLM_ASSISTED_ANALYZER_H
