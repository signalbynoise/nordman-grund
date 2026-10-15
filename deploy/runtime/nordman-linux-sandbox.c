/*
 * nordman-linux-sandbox.c
 * Kernel-level process hardening launcher for untrusted workspace commands on Linux.
 * Enforces PR_SET_NO_NEW_PRIVS, PR_SET_DUMPABLE=0, and RLIMIT_CORE=0 before execvp.
 */
#include <stdio.h>
#include <stdlib.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <unistd.h>

int main(int argc, char **argv) {
  if (argc < 2) {
    fprintf(stderr, "Usage: nordman-linux-sandbox <command> [args...]\n");
    return 1;
  }

  /* Prevent any privilege escalation via setuid/setgid/file capabilities */
  if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) {
    perror("prctl(PR_SET_NO_NEW_PRIVS)");
    return 1;
  }

  /* Prevent ptrace / core dump memory inspection across processes */
  (void)prctl(PR_SET_DUMPABLE, 0, 0, 0, 0);

  struct rlimit zero_core = {0, 0};
  (void)setrlimit(RLIMIT_CORE, &zero_core);

  execvp(argv[1], &argv[1]);
  perror("execvp");
  return 127;
}
