#include "DESAN/LLMAssistedAnalyzer.h"

#include "llvm/ADT/SmallPtrSet.h"
#include "llvm/ADT/SmallString.h"
#include "llvm/ADT/SmallVector.h"
#include "llvm/IR/BasicBlock.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/Instructions.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/MemoryBuffer.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/IR/CFG.h"

#include <cstdlib>
#include <system_error>
#include <utility>

using namespace llvm;

namespace desan {

namespace {

std::string valueAsOperand(Value *V) {
  if (!V)
    return "<null>";

  std::string Text;
  raw_string_ostream OS(Text);
  V->printAsOperand(OS, false);
  return OS.str();
}

std::string instructionText(const Instruction *I) {
  if (!I)
    return "<null>";

  std::string Text;
  raw_string_ostream OS(Text);
  I->print(OS);
  return OS.str();
}

std::string shellQuote(StringRef Text) {
  std::string Quoted = "'";
  for (char C : Text) {
    if (C == '\'')
      Quoted += "'\\''";
    else
      Quoted += C;
  }
  Quoted += "'";
  return Quoted;
}

void collectBackwardInstructions(Value *V, SmallPtrSetImpl<Value *> &Visited,
                                 SmallVectorImpl<Instruction *> &Out,
                                 unsigned Depth, unsigned MaxInstructions) {
  if (!V || Depth > 8 || Out.size() >= MaxInstructions)
    return;
  if (!Visited.insert(V).second)
    return;

  auto *I = dyn_cast<Instruction>(V);
  if (!I)
    return;

  for (Value *Operand : I->operands()) {
    if (Out.size() >= MaxInstructions)
      break;
    collectBackwardInstructions(Operand, Visited, Out, Depth + 1,
                                MaxInstructions);
  }

  if (Out.size() < MaxInstructions)
    Out.push_back(I);
}

} // namespace

LLMAssistedAnalyzer::LLMAssistedAnalyzer(std::string Command,
                                         unsigned MaxSliceInstructions)
    : Command(std::move(Command)),
      MaxSliceInstructions(MaxSliceInstructions ? MaxSliceInstructions : 32) {}

std::string LLMAssistedAnalyzer::summarizeIRSlice(CallBase *CB) const {
  std::string Summary;
  raw_string_ostream OS(Summary);

  if (!CB) {
    OS << "<null sanitizer check>\n";
    return OS.str();
  }

  Function *F = CB->getFunction();
  BasicBlock *BB = CB->getParent();

  OS << "Function: ";
  if (F && F->hasName())
    OS << F->getName();
  else
    OS << "<unknown>";
  OS << "\n";

  OS << "BasicBlock: ";
  if (BB && BB->hasName())
    OS << BB->getName();
  else if (BB)
    OS << "<unnamed>";
  else
    OS << "<unknown>";
  OS << "\n\n";

  SmallVector<Instruction *, 32> Context;
  if (BB) {
    for (Instruction &I : *BB) {
      if (&I == CB)
        break;
      Context.push_back(&I);
    }
  }

  OS << "Local context before sanitizer call:\n";
  unsigned ContextStart = Context.size() > 8 ? Context.size() - 8 : 0;
  for (unsigned I = ContextStart; I < Context.size(); ++I)
    OS << instructionText(Context[I]) << "\n";
  if (Context.empty())
    OS << "<none>\n";
  OS << "\n";

  SmallPtrSet<Value *, 32> Visited;
  SmallVector<Instruction *, 32> BackwardSlice;
  for (Value *Operand : CB->operands())
    collectBackwardInstructions(Operand, Visited, BackwardSlice, 0,
                                MaxSliceInstructions);

  OS << "Backward data slice:\n";
  for (Instruction *I : BackwardSlice) {
    if (I != CB)
      OS << instructionText(I) << "\n";
  }
  if (BackwardSlice.empty())
    OS << "<none>\n";
  OS << "\n";

  OS << "Sanitizer call:\n";
  OS << instructionText(CB) << "\n\n";

  OS << "Control-flow context:\n";
  if (BB) {
    for (BasicBlock *Pred : predecessors(BB)) {
      OS << "Predecessor terminator: "
         << instructionText(Pred ? Pred->getTerminator() : nullptr) << "\n";
    }
    if (!pred_empty(BB))
      OS << "Current terminator: " << instructionText(BB->getTerminator())
         << "\n";
    else
      OS << "<no predecessors>\n";
  } else {
    OS << "<unknown>\n";
  }

  return OS.str();
}

LLMQueryResult LLMAssistedAnalyzer::askIfSameCheckedVariable(
    const CheckedVariable &LHS, const CheckedVariable &RHS) const {
  std::string Prompt;
  raw_string_ostream OS(Prompt);

  OS << "You are assisting an LLVM sanitizer-check optimizer.\n";
  OS << "Determine whether the two checked values semantically correspond to "
        "the same high-level variable.\n";
  OS << "Be conservative. If aliasing, PHI, select, or casts make this "
        "uncertain, return UNKNOWN.\n";
  OS << "Your answer is advisory only. The optimizer will not delete checks "
        "unless static analysis independently proves safety.\n\n";
  OS << "Checked value A:\n" << checkedVariableSummary(LHS) << "\n";
  if (LHS.CheckInst)
    OS << "IR slice A:\n" << summarizeIRSlice(LHS.CheckInst) << "\n";
  OS << "Checked value B:\n" << checkedVariableSummary(RHS) << "\n";
  if (RHS.CheckInst)
    OS << "IR slice B:\n" << summarizeIRSlice(RHS.CheckInst) << "\n";
  OS << "Return JSON:\n";
  OS << "{\n";
  OS << "  \"same_checked_variable\": \"YES | NO | UNKNOWN\",\n";
  OS << "  \"confidence\": 0.0,\n";
  OS << "  \"reason\": \"...\"\n";
  OS << "}\n";

  return runPrompt(OS.str());
}

LLMQueryResult LLMAssistedAnalyzer::askIfCheckIsReadOrWrite(
    CallBase *CB) const {
  return runPrompt(buildCheckQuestion(CB));
}

LLMQueryResult
LLMAssistedAnalyzer::askIfSafeToRemove(const CheckNode *N,
                                       bool StaticPolicyCandidate) const {
  std::string Prompt;
  raw_string_ostream OS(Prompt);

  OS << "You are assisting an LLVM sanitizer-check optimizer.\n";
  OS << "Explain whether this sanitizer check appears redundant. This answer "
        "is advisory only and must not be used as the deletion decision.\n";
  OS << "The current static pass deletes only READ checks selected by its "
        "per-variable retention policy; LLM output is explanation-only.\n";
  OS << "Static policy candidate: "
     << (StaticPolicyCandidate ? "true" : "false") << "\n\n";

  if (!N || !N->CheckInst) {
    OS << "Check: <null>\n";
  } else {
    OS << "Check node:\n";
    OS << "Sanitizer: " << sanitizerKindName(N->Var.Sanitizer) << "\n";
    OS << "Access Type: " << accessTypeName(N->Type) << "\n";
    OS << checkedVariableSummary(N->Var) << "\n";
    OS << "IR slice:\n" << summarizeIRSlice(N->CheckInst) << "\n";
  }

  OS << "Return JSON:\n";
  OS << "{\n";
  OS << "  \"appears_redundant\": \"YES | NO | UNKNOWN\",\n";
  OS << "  \"static_analysis_must_decide\": true,\n";
  OS << "  \"confidence\": 0.0,\n";
  OS << "  \"reason\": \"...\"\n";
  OS << "}\n";

  return runPrompt(OS.str());
}

void LLMAssistedAnalyzer::dumpResult(raw_ostream &OS, StringRef Title,
                                     const LLMQueryResult &Result,
                                     bool IncludePrompt) const {
  OS << "DESAN LLM Assist: " << Title << "\n";
  OS << "Invoked: " << (Result.Invoked ? "yes" : "no") << "\n";
  OS << "Succeeded: " << (Result.Succeeded ? "yes" : "no") << "\n";
  if (Result.Invoked)
    OS << "ExitCode: " << Result.ExitCode << "\n";
  if (!Result.Error.empty())
    OS << "Error: " << Result.Error << "\n";
  if (IncludePrompt)
    OS << "Prompt:\n" << Result.Prompt << "\n";
  if (!Result.Response.empty())
    OS << "Response:\n" << Result.Response << "\n";
  OS << "End DESAN LLM Assist\n";
}

std::string LLMAssistedAnalyzer::buildCheckQuestion(CallBase *CB) const {
  std::string Prompt;
  raw_string_ostream OS(Prompt);

  OS << "Given the following LLVM IR slice, identify the high-level variable "
        "being checked by the sanitizer call.\n";
  OS << "Also infer whether the check corresponds to a read or write access.\n";
  OS << "Be conservative. If uncertain, return UNKNOWN.\n";
  OS << "This result is advisory only; the optimizer will not delete checks "
        "unless static analysis independently proves safety.\n\n";
  OS << "LLVM IR:\n";
  OS << summarizeIRSlice(CB) << "\n";
  OS << "Return JSON:\n";
  OS << "{\n";
  OS << "  \"checked_variable\": \"...\",\n";
  OS << "  \"access_type\": \"READ | WRITE | UNKNOWN\",\n";
  OS << "  \"confidence\": 0.0,\n";
  OS << "  \"reason\": \"...\"\n";
  OS << "}\n";

  return OS.str();
}

std::string
LLMAssistedAnalyzer::checkedVariableSummary(const CheckedVariable &Var) const {
  std::string Text;
  raw_string_ostream OS(Text);

  OS << "Sanitizer: " << sanitizerKindName(Var.Sanitizer) << "\n";
  OS << "Access Type: " << accessTypeName(Var.Type) << "\n";
  OS << "Base: " << valueAsOperand(Var.Base) << "\n";
  OS << "Offsets:";
  if (Var.Offsets.empty()) {
    OS << " <none>\n";
  } else {
    OS << "\n";
    for (Value *Offset : Var.Offsets)
      OS << "  - " << valueAsOperand(Offset) << "\n";
  }
  OS << "Region: ";
  if (Var.HasStaticByteOffset)
    OS << "static-offset=" << Var.StaticByteOffset;
  else
    OS << "static-offset=<unknown>";
  OS << ", access-size=";
  if (Var.AccessSize != 0)
    OS << Var.AccessSize;
  else
    OS << "<unknown>";
  OS << "\n";
  if (Var.CheckInst)
    OS << "Check: " << instructionText(Var.CheckInst) << "\n";

  return OS.str();
}

LLMQueryResult LLMAssistedAnalyzer::runPrompt(std::string Prompt) const {
  LLMQueryResult Result;
  Result.Prompt = std::move(Prompt);

  if (Command.empty())
    return Result;

  int PromptFD = -1;
  int ResponseFD = -1;
  SmallString<128> PromptPath;
  SmallString<128> ResponsePath;

  std::error_code EC =
      sys::fs::createTemporaryFile("desan-llm-prompt", "txt", PromptFD,
                                   PromptPath);
  if (EC) {
    Result.Error = "cannot create prompt temp file: " + EC.message();
    return Result;
  }

  EC = sys::fs::createTemporaryFile("desan-llm-response", "json", ResponseFD,
                                    ResponsePath);
  if (EC) {
    sys::fs::remove(PromptPath);
    Result.Error = "cannot create response temp file: " + EC.message();
    return Result;
  }

  {
    raw_fd_ostream PromptOS(PromptFD, true);
    PromptOS << Result.Prompt;
  }
  {
    raw_fd_ostream ResponseOS(ResponseFD, true);
  }

  std::string FullCommand = Command + " < " + shellQuote(PromptPath) + " > " +
                            shellQuote(ResponsePath);
  Result.Invoked = true;
  Result.ExitCode = std::system(FullCommand.c_str());

  if (Result.ExitCode == 0) {
    auto BufferOrErr = MemoryBuffer::getFile(ResponsePath);
    if (BufferOrErr) {
      Result.Response = (*BufferOrErr)->getBuffer().str();
      Result.Succeeded = true;
    } else {
      Result.Error =
          "cannot read response temp file: " + BufferOrErr.getError().message();
    }
  } else {
    Result.Error = "LLM command returned non-zero status";
  }

  sys::fs::remove(PromptPath);
  sys::fs::remove(ResponsePath);
  return Result;
}

} // namespace desan
