# Applied on top of php/init.sls for the staging host only (see pillar/top.sls).
# Staging is a low-traffic canary box, so OPcache gets a much smaller budget
# than the production mw*/task* fleet.
php:
  opcache:
    memory_consumption: 256
    interned_strings_buffer: 8
    max_accelerated_files: 20000
    jit_buffer_size: 32M
