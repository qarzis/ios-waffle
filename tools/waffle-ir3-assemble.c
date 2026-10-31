#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "common/freedreno_dev_info.h"
#include "ir3/ir3_assembler.h"
#include "ir3/ir3_compiler.h"
#include "ir3/ir3_shader.h"

int main(int argc, char **argv)
{
    if (argc != 5) {
        fprintf(stderr, "usage: %s input.asm shader.bin metadata.json disasm.txt\n", argv[0]);
        return 2;
    }
    const struct fd_dev_id id = {.gpu_id=750, .chip_id=0x43051401};
    const struct fd_dev_info *info = fd_dev_info_raw(&id);
    struct ir3_compiler_options options = {.disable_cache=true};
    if (!info || fd_dev_gen(&id) != 7) return 3;
    struct ir3_compiler *compiler = ir3_compiler_create(NULL, &id, info, &options);
    if (!compiler) return 4;
    FILE *input = fopen(argv[1], "r");
    if (!input) return 5;
    struct ir3_kernel_info kernel = {0};
    struct ir3_shader *shader = ir3_parse_asm(compiler, &kernel, input);
    fclose(input);
    if (!shader || !shader->variants || !shader->variants->bin) return 6;
    struct ir3_shader_variant *v = shader->variants;
    FILE *binary = fopen(argv[2], "wb"), *metadata = fopen(argv[3], "w"), *disasm = fopen(argv[4], "w");
    if (!binary || !metadata || !disasm) return 7;
    if (fwrite(v->bin, 1, v->info.size, binary) != v->info.size) return 8;
    fprintf(metadata,
        "{\n  \"chip_id\": \"0x43051401\", \"generation\": 7,\n"
        "  \"binary_bytes\": %u, \"instruction_dwords\": %u, \"instrlen\": %u,\n"
        "  \"max_reg\": %d, \"max_half_reg\": %d, \"constlen\": %u,\n"
        "  \"local_size\": [%u, %u, %u], \"buffer_count\": %u,\n",
        v->info.size, v->info.sizedwords, v->instrlen, v->info.max_reg,
        v->info.max_half_reg, v->constlen, v->local_size[0], v->local_size[1], v->local_size[2], kernel.num_bufs);
    fprintf(metadata,
        "  \"local_invocation_id_regid\": %u, \"work_group_id_regid\": %u,\n"
        "  \"branchstack_hw\": %u, \"shared_bytes\": %u,\n"
        "  \"mergedregs\": %s, \"early_preamble\": %s, \"double_threadsize\": %s,\n",
        ir3_find_sysval_regid(v, SYSTEM_VALUE_LOCAL_INVOCATION_ID),
        ir3_find_sysval_regid(v, SYSTEM_VALUE_WORKGROUP_ID), ir3_shader_branchstack_hw(v),
        v->shared_size, v->mergedregs ? "true" : "false", v->early_preamble ? "true" : "false",
        v->info.double_threadsize ? "true" : "false");
    fprintf(metadata, "  \"buffer_dwords\": [");
    for (unsigned n=0; n<kernel.num_bufs; ++n) fprintf(metadata, "%s%u", n ? ", " : "", kernel.buf_sizes[n]);
    fprintf(metadata, "],\n  \"device_opened\": false, \"gpu_executed\": false\n}\n");
    struct ir3_disasm_options disasm_options = {.out=disasm, .print_raw=true};
    ir3_shader_disasm_options(v, (uint32_t *)v->bin, &disasm_options);
    if (fclose(binary) || fclose(metadata) || fclose(disasm)) return 9;
    ir3_compiler_destroy(compiler);
    return 0;
}
