#ifndef DESAN_SANITIZER_CHECK_COLLECTOR_H
#define DESAN_SANITIZER_CHECK_COLLECTOR_H

#include "llvm/ADT/SmallVector.h"
#include "llvm/ADT/StringRef.h"
#include "llvm/IR/InstrTypes.h"
#include "llvm/Support/raw_ostream.h"

#include <cstdint>
#include <map>
#include <optional>
#include <string>

namespace llvm {
class Function;
} // namespace llvm

namespace desan {

enum class SanitizerKind {
  ASan,
  UBSan,
  MemSan,
  Unknown,
};

llvm::StringRef sanitizerKindName(SanitizerKind Kind);

class SanitizerCheckCollector {
public:
  struct ClassifiedCheck {
    SanitizerKind Sanitizer = SanitizerKind::Unknown;
    std::string CheckType;
  };

  struct CheckStat {
    SanitizerKind Sanitizer = SanitizerKind::Unknown;
    std::string CheckType;
    uint64_t Count = 0;
    double RatioWithinSanitizer = 0.0;
    double RatioOverall = 0.0;
    double RuntimeRatio = -1.0;
  };

  void collectChecks(llvm::Function &F);

  std::optional<ClassifiedCheck> classifyCheck(llvm::CallBase *CB) const;

  void dumpCheckStatistics(llvm::raw_ostream &OS = llvm::errs()) const;

  llvm::SmallVector<CheckStat, 16>
  identifyCoreChecks(unsigned MaxPerSanitizer = 4,
                     double MinRatioWithinSanitizer = 5.0) const;

  bool loadProfile(llvm::StringRef ProfilePath,
                   llvm::raw_ostream *ErrorOS = nullptr);

  uint64_t getTotalChecks() const { return TotalChecks; }

private:
  using CheckCountMap = std::map<std::string, uint64_t>;

  void recordCheck(const ClassifiedCheck &Check);

  llvm::SmallVector<CheckStat, 16>
  getStatsForSanitizer(SanitizerKind Sanitizer) const;

  std::map<SanitizerKind, CheckCountMap> CheckCounts;
  std::map<SanitizerKind, uint64_t> SanitizerTotals;
  std::map<std::string, double> RuntimeCosts;
  double TotalRuntimeCost = 0.0;
  uint64_t TotalChecks = 0;
};

} // namespace desan

#endif // DESAN_SANITIZER_CHECK_COLLECTOR_H
