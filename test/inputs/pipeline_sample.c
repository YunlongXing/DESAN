#include <stddef.h>
#include <stdint.h>

static int sum_array(const int *values, size_t count) {
  int sum = 0;
  for (size_t i = 0; i < count; ++i)
    sum += values[i];
  return sum;
}

static uintptr_t pointer_roundtrip(int *ptr) {
  uintptr_t raw = (uintptr_t)ptr;
  return raw + 0;
}

int main(void) {
  int values[4] = {1, 2, 3, 4};
  int total = sum_array(values, 4);
  uintptr_t raw = pointer_roundtrip(values);
  return total == 10 && raw != 0 ? 0 : 1;
}
