#ifndef DESAN_CHECKED_VARIABLE_ANALYZER_H
#define DESAN_CHECKED_VARIABLE_ANALYZER_H

#include "DESAN/SanitizerCheckCollector.h"

#include "llvm/ADT/SmallPtrSet.h"
#include "llvm/ADT/SmallVector.h"
#include "llvm/IR/InstrTypes.h"
#include "llvm/IR/Value.h"
#include "llvm/Support/raw_ostream.h"

#include <cstdint>
#include <optional>

namespace llvm {
class DataLayout;
} // namespace llvm

namespace desan {

enum class AccessType {
  READ,
  WRITE,
  UNKNOWN,
};

llvm::StringRef accessTypeName(AccessType Type);

struct CheckedVariable {
  llvm::Value *Base = nullptr;
  llvm::Value *Address = nullptr;
  llvm::SmallVector<llvm::Value *, 4> Offsets;
  bool HasStaticByteOffset = false;
  int64_t StaticByteOffset = 0;
  uint64_t AccessSize = 0;
  AccessType Type = AccessType::UNKNOWN;
  SanitizerKind Sanitizer = SanitizerKind::Unknown;
  llvm::CallBase *CheckInst = nullptr;
};

class CheckedVariableAnalyzer {
public:
  std::optional<CheckedVariable> analyzeCheck(llvm::CallBase *CB);

  CheckedVariable traceCheckedValue(llvm::Value *V);

  llvm::Value *normalizeVariable(llvm::Value *V);

  AccessType inferAccessType(llvm::CallBase *CB);

private:
  using ClassifiedCheck = SanitizerCheckCollector::ClassifiedCheck;

  std::optional<ClassifiedCheck> classifyCheck(llvm::CallBase *CB) const;

  llvm::Value *getCheckedOperand(llvm::CallBase *CB,
                                 const ClassifiedCheck &Check) const;

  llvm::Value *getImplicitMemSanOperand(llvm::CallBase *CB,
                                        llvm::StringRef CheckType) const;

  llvm::Value *getUBSanCheckedOperand(llvm::CallBase *CB,
                                      llvm::StringRef CheckType) const;

  llvm::Value *findUBSanOutOfBoundsAccessOperand(llvm::CallBase *CB,
                                                 llvm::Value *Index) const;

  uint64_t inferASanAccessSize(llvm::CallBase *CB,
                               llvm::StringRef CheckType) const;

  uint64_t inferMemSanAccessSize(llvm::CallBase *CB,
                                 llvm::StringRef CheckType,
                                 llvm::Value *CheckedValue);

  uint64_t inferAccessSizeFromUses(llvm::Value *CheckedValue);

  CheckedVariable traceASanCheckedAddress(llvm::Value *V);

  CheckedVariable traceASanCheckedAddressImpl(
      llvm::Value *V, llvm::SmallPtrSetImpl<llvm::Value *> &Visited,
      unsigned Depth);

  CheckedVariable traceCheckedValueImpl(
      llvm::Value *V, llvm::SmallPtrSetImpl<llvm::Value *> &Visited,
      unsigned Depth);

  llvm::Value *
  normalizeVariableImpl(llvm::Value *V,
                        llvm::SmallPtrSetImpl<llvm::Value *> &Visited,
                        unsigned Depth);

  AccessType inferAccessTypeFromUses(llvm::Value *CheckedValue,
                                     llvm::CallBase *CheckInst);

  SanitizerCheckCollector Collector;
  const llvm::DataLayout *CurrentDL = nullptr;
};

void printCheckedVariable(llvm::raw_ostream &OS,
                          const CheckedVariable &Variable);

} // namespace desan

#endif // DESAN_CHECKED_VARIABLE_ANALYZER_H
