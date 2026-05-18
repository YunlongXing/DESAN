#include "DESAN/SanitizerCheckCollector.h"

#include "llvm/ADT/SmallVector.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/ADT/StringRef.h"
#include "llvm/ADT/STLExtras.h"
#include "llvm/ADT/Twine.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/GlobalAlias.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/IR/Instructions.h"
#include "llvm/Support/Format.h"
#include "llvm/Support/MemoryBuffer.h"

#include <algorithm>
#include <cstdlib>
#include <memory>
#include <utility>

using namespace llvm;

namespace desan {

StringRef sanitizerKindName(SanitizerKind Kind) {
  switch (Kind) {
  case SanitizerKind::ASan:
    return "ASan";
  case SanitizerKind::UBSan:
    return "UBSan";
  case SanitizerKind::MemSan:
    return "MemSan";
  case SanitizerKind::Unknown:
    return "Unknown";
  }
  return "Unknown";
}

static std::string runtimeCostKey(SanitizerKind Sanitizer, StringRef CheckType) {
  return (Twine(sanitizerKindName(Sanitizer)) + "\t" + CheckType).str();
}

static std::string canonicalCalleeName(StringRef Name) {
  Name = Name.trim();
  Name.consume_front("\01");

  // Mach-O IR can expose an extra C symbol prefix. Keep the canonical
  // sanitizer runtime spelling so Linux and Darwin inputs aggregate together.
  if (Name.starts_with("___asan_") || Name.starts_with("___ubsan_") ||
      Name.starts_with("___msan_"))
    Name = Name.drop_front();

  return Name.str();
}

static const Function *resolveCalledFunction(const CallBase *CB) {
  if (const Function *Callee = CB->getCalledFunction())
    return Callee;

  const Value *Called = CB->getCalledOperand();
  if (!Called)
    return nullptr;

  Called = Called->stripPointerCasts();
  if (const auto *Callee = dyn_cast<Function>(Called))
    return Callee;

  if (const auto *Alias = dyn_cast<GlobalAlias>(Called)) {
    const GlobalObject *Aliasee = Alias->getAliaseeObject();
    return dyn_cast_or_null<Function>(Aliasee);
  }

  return nullptr;
}

static bool isASanCheckName(StringRef Name) {
  return Name.starts_with("__asan_report_load") ||
         Name.starts_with("__asan_report_store") ||
         Name.starts_with("__asan_report_exp_load") ||
         Name.starts_with("__asan_report_exp_store") ||
         Name.starts_with("__asan_report_error") ||
         Name.starts_with("__asan_load") || Name.starts_with("__asan_store") ||
         Name.starts_with("__asan_exp_load") ||
         Name.starts_with("__asan_exp_store") ||
         Name.starts_with("__asan_memcpy") ||
         Name.starts_with("__asan_memmove") ||
         Name.starts_with("__asan_memset") ||
         Name == "__asan_handle_no_return";
}

static bool isUBSanCheckName(StringRef Name) {
  return Name.starts_with("__ubsan_handle_") || Name == "llvm.ubsantrap";
}

static bool isMemSanCheckName(StringRef Name) {
  return Name.starts_with("__msan_warning") ||
         Name.starts_with("__msan_maybe_warning") ||
         Name.starts_with("__msan_param_") ||
         Name.starts_with("__msan_retval_") ||
         Name.starts_with("__msan_va_arg_") ||
         Name.starts_with("__msan_check_mem_is_initialized") ||
         Name.starts_with("__msan_test_shadow") ||
         Name.starts_with("__msan_print_shadow");
}

static SanitizerKind classifySanitizerName(StringRef Name) {
  if (isASanCheckName(Name))
    return SanitizerKind::ASan;
  if (isUBSanCheckName(Name))
    return SanitizerKind::UBSan;
  if (isMemSanCheckName(Name))
    return SanitizerKind::MemSan;
  return SanitizerKind::Unknown;
}

static bool parseDouble(StringRef Text, double &Value) {
  Text = Text.trim();
  if (Text.empty())
    return false;

  std::string Storage = Text.str();
  char *End = nullptr;
  Value = std::strtod(Storage.c_str(), &End);
  return End != Storage.c_str() && *End == '\0';
}

static SanitizerKind parseSanitizerKind(StringRef Text) {
  Text = Text.trim();
  if (Text.equals_insensitive("asan"))
    return SanitizerKind::ASan;
  if (Text.equals_insensitive("ubsan"))
    return SanitizerKind::UBSan;
  if (Text.equals_insensitive("memsan") || Text.equals_insensitive("msan"))
    return SanitizerKind::MemSan;
  return SanitizerKind::Unknown;
}

void SanitizerCheckCollector::collectChecks(Function &F) {
  for (Instruction &I : instructions(F)) {
    auto *CB = dyn_cast<CallBase>(&I);
    if (!CB)
      continue;

    if (std::optional<ClassifiedCheck> Check = classifyCheck(CB))
      recordCheck(*Check);
  }
}

std::optional<SanitizerCheckCollector::ClassifiedCheck>
SanitizerCheckCollector::classifyCheck(CallBase *CB) const {
  if (!CB)
    return std::nullopt;

  const Function *Callee = resolveCalledFunction(CB);
  if (!Callee || Callee->getName().empty())
    return std::nullopt;

  std::string NameStorage = canonicalCalleeName(Callee->getName());
  StringRef Name(NameStorage);
  SanitizerKind Sanitizer = classifySanitizerName(Name);
  if (Sanitizer == SanitizerKind::Unknown)
    return std::nullopt;

  return ClassifiedCheck{Sanitizer, Name.str()};
}

void SanitizerCheckCollector::recordCheck(const ClassifiedCheck &Check) {
  if (Check.Sanitizer == SanitizerKind::Unknown || Check.CheckType.empty())
    return;

  ++CheckCounts[Check.Sanitizer][Check.CheckType];
  ++SanitizerTotals[Check.Sanitizer];
  ++TotalChecks;
}

SmallVector<SanitizerCheckCollector::CheckStat, 16>
SanitizerCheckCollector::getStatsForSanitizer(SanitizerKind Sanitizer) const {
  SmallVector<CheckStat, 16> Stats;
  auto CountsIt = CheckCounts.find(Sanitizer);
  if (CountsIt == CheckCounts.end())
    return Stats;

  uint64_t SanitizerTotal = 0;
  if (auto TotalIt = SanitizerTotals.find(Sanitizer);
      TotalIt != SanitizerTotals.end())
    SanitizerTotal = TotalIt->second;

  for (const auto &Check : CountsIt->second) {
    CheckStat Stat;
    Stat.Sanitizer = Sanitizer;
    Stat.CheckType = Check.first;
    Stat.Count = Check.second;
    Stat.RatioWithinSanitizer =
        SanitizerTotal == 0 ? 0.0
                            : (100.0 * static_cast<double>(Check.second) /
                               static_cast<double>(SanitizerTotal));
    Stat.RatioOverall =
        TotalChecks == 0 ? 0.0
                         : (100.0 * static_cast<double>(Check.second) /
                            static_cast<double>(TotalChecks));

    auto RuntimeIt =
        RuntimeCosts.find(runtimeCostKey(Sanitizer, Stat.CheckType));
    if (RuntimeIt != RuntimeCosts.end() && TotalRuntimeCost > 0.0)
      Stat.RuntimeRatio = 100.0 * RuntimeIt->second / TotalRuntimeCost;

    Stats.push_back(std::move(Stat));
  }

  llvm::sort(Stats, [](const CheckStat &LHS, const CheckStat &RHS) {
    if (LHS.Count != RHS.Count)
      return LHS.Count > RHS.Count;
    return LHS.CheckType < RHS.CheckType;
  });

  return Stats;
}

void SanitizerCheckCollector::dumpCheckStatistics(raw_ostream &OS) const {
  OS << "DESAN Sanitizer Check Statistics\n";
  OS << "Total Checks: " << TotalChecks << "\n\n";

  for (SanitizerKind Sanitizer :
       {SanitizerKind::ASan, SanitizerKind::UBSan, SanitizerKind::MemSan}) {
    uint64_t SanitizerTotal = 0;
    if (auto TotalIt = SanitizerTotals.find(Sanitizer);
        TotalIt != SanitizerTotals.end())
      SanitizerTotal = TotalIt->second;

    OS << "Sanitizer: " << sanitizerKindName(Sanitizer) << "\n";
    OS << "Total Checks: " << SanitizerTotal << "\n";

    SmallVector<CheckStat, 16> Stats = getStatsForSanitizer(Sanitizer);
    if (Stats.empty()) {
      OS << "\n";
      continue;
    }

    for (const CheckStat &Stat : Stats) {
      OS << "Check Type: " << Stat.CheckType << "\n";
      OS << "Count: " << Stat.Count << "\n";
      OS << "Ratio: ";
      OS << format("%.1f%%", Stat.RatioWithinSanitizer) << "\n";
      OS << "Overall Ratio: ";
      OS << format("%.1f%%", Stat.RatioOverall) << "\n";
      if (Stat.RuntimeRatio >= 0.0) {
        OS << "Runtime Ratio: ";
        OS << format("%.1f%%", Stat.RuntimeRatio) << "\n";
      }
      OS << "\n";
    }
  }

  OS << "End Sanitizer Check Statistics\n";
}

SmallVector<SanitizerCheckCollector::CheckStat, 16>
SanitizerCheckCollector::identifyCoreChecks(
    unsigned MaxPerSanitizer, double MinRatioWithinSanitizer) const {
  SmallVector<CheckStat, 16> CoreChecks;

  for (SanitizerKind Sanitizer :
       {SanitizerKind::ASan, SanitizerKind::UBSan, SanitizerKind::MemSan}) {
    SmallVector<CheckStat, 16> Stats = getStatsForSanitizer(Sanitizer);
    if (Stats.empty())
      continue;

    unsigned Added = 0;
    for (const CheckStat &Stat : Stats) {
      if (MaxPerSanitizer != 0 && Added >= MaxPerSanitizer)
        break;

      if (Stat.RatioWithinSanitizer < MinRatioWithinSanitizer && Added > 0)
        continue;

      CoreChecks.push_back(Stat);
      ++Added;
    }
  }

  llvm::sort(CoreChecks, [](const CheckStat &LHS, const CheckStat &RHS) {
    if (LHS.Count != RHS.Count)
      return LHS.Count > RHS.Count;
    if (LHS.Sanitizer != RHS.Sanitizer)
      return sanitizerKindName(LHS.Sanitizer) <
             sanitizerKindName(RHS.Sanitizer);
    return LHS.CheckType < RHS.CheckType;
  });

  return CoreChecks;
}

bool SanitizerCheckCollector::loadProfile(StringRef ProfilePath,
                                          raw_ostream *ErrorOS) {
  RuntimeCosts.clear();
  TotalRuntimeCost = 0.0;

  if (ProfilePath.empty())
    return true;

  ErrorOr<std::unique_ptr<MemoryBuffer>> BufferOrErr =
      MemoryBuffer::getFile(ProfilePath);
  if (!BufferOrErr) {
    if (ErrorOS)
      *ErrorOS << "DESAN: failed to read profile file '" << ProfilePath
               << "': " << BufferOrErr.getError().message() << "\n";
    return false;
  }

  SmallVector<StringRef, 4> Lines;
  (*BufferOrErr)->getBuffer().split(Lines, '\n');

  for (StringRef Line : Lines) {
    Line = Line.trim();
    if (Line.empty() || Line.starts_with("#"))
      continue;

    SmallVector<StringRef, 4> Fields;
    if (Line.contains(","))
      Line.split(Fields, ',', -1, false);
    else
      SplitString(Line, Fields);

    for (StringRef &Field : Fields)
      Field = Field.trim();

    SanitizerKind Sanitizer = SanitizerKind::Unknown;
    std::string CheckTypeStorage;
    double Cost = 0.0;

    if (Fields.size() == 2) {
      CheckTypeStorage = canonicalCalleeName(Fields[0]);
      Sanitizer = classifySanitizerName(CheckTypeStorage);
      if (!parseDouble(Fields[1], Cost))
        continue;
    } else if (Fields.size() >= 3) {
      Sanitizer = parseSanitizerKind(Fields[0]);
      CheckTypeStorage = canonicalCalleeName(Fields[1]);
      if (!parseDouble(Fields[2], Cost))
        continue;
    } else {
      continue;
    }

    if (Sanitizer == SanitizerKind::Unknown || CheckTypeStorage.empty() ||
        Cost < 0.0)
      continue;

    RuntimeCosts[runtimeCostKey(Sanitizer, CheckTypeStorage)] += Cost;
    TotalRuntimeCost += Cost;
  }

  return true;
}

} // namespace desan
