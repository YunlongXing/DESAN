#include <stdint.h>
#include <string.h>

static int trigger_asan(void) {
  volatile int values[1] = {0};
  return values[4];
}

static int trigger_ubsan(void) {
  volatile int shift = 31;
  return 1 << shift;
}

static int trigger_msan(int argc) {
  int maybe_uninit;
  if (argc == 12345)
    maybe_uninit = 7;
  return maybe_uninit;
}

int main(int argc, char **argv) {
  if (argc < 2)
    return 0;
  if (strcmp(argv[1], "asan") == 0)
    return trigger_asan();
  if (strcmp(argv[1], "ubsan") == 0)
    return trigger_ubsan();
  if (strcmp(argv[1], "msan") == 0)
    return trigger_msan(argc);
  return 0;
}
