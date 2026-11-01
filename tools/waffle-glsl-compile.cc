/* Offline GLSL -> linked Mesa NIR -> FD750 IR3, no device or submission. */
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include "main/mtypes.h"
#include "pipe/p_screen.h"
#include "compiler/glsl/standalone.h"
#include "compiler/glsl/standalone_scaffolding.h"
#include "compiler/glsl/linker_util.h"
#include "compiler/glsl/gl_nir_linker.h"
#include "compiler/glsl/gl_nir.h"
#include "compiler/nir/nir.h"
#include "common/freedreno_dev_info.h"
#include "ir3/ir3_compiler.h"
#include "ir3/ir3_shader.h"
#include "ir3/ir3_nir.h"
extern "C" {
#include "ir3/ir3_descriptor.h"
}
extern "C" ir3_shader_variant *waffle_glsl_variant(char *filename)
{
    const fd_dev_id id={.gpu_id=750,.chip_id=0x43051401};
    ir3_compiler_options compiler_options={};compiler_options.disable_cache=true;
    ir3_compiler *compiler=ir3_compiler_create(nullptr,&id,fd_dev_info_raw(&id),&compiler_options);assert(compiler);
    static gl_context context;
    standalone_options options={};options.glsl_version=450;
    gl_shader_program *program=standalone_compile_shader(&options,1,&filename,&context);
    if(!program || program->NumShaders!=1 || !program->Shaders[0]->CompileStatus)return nullptr;
    assert(program->Shaders[0]->Stage==MESA_SHADER_COMPUTE);
    /* Standalone sets options only for VS/FS; use the actual backend options
     * for CS before invoking the same public linker path as standalone.cpp. */
    context.screen->nir_options[MESA_SHADER_COMPUTE]=&compiler->nir_options;
    /* freedreno_screen.c caps -> st_extensions.c constants, required by linker. */
    context.Const.GLSLTessLevelsAsInputs=true;
    /* CS SSBO count from freedreno_screen.c/ir3_descriptor.h, propagated as
     * in st_extensions.c. This offline context only exposes the CS stage. */
    context.Const.Program[MESA_SHADER_COMPUTE].MaxShaderStorageBlocks=IR3_BINDLESS_SSBO_COUNT;
    context.Const.MaxCombinedShaderStorageBlocks=IR3_BINDLESS_SSBO_COUNT;
    context.Const.MaxShaderStorageBufferBindings=IR3_BINDLESS_SSBO_COUNT;
    context.Const.MaxCombinedShaderOutputResources+=IR3_BINDLESS_SSBO_COUNT;
    program->Shaders[0]->nir->options=&compiler->nir_options;
    _mesa_clear_shader_program_data(&context,program);
    program->data->LinkStatus=LINKING_SUCCESS;
    link_shaders_init(&context,program);
    gl_nir_link_glsl(&context,program);
    if(!program->data->LinkStatus){std::fprintf(stderr,"link: %s\n",program->data->InfoLog);return nullptr;}
    nir_shader *nir=nir_shader_clone(nullptr,program->_LinkedShaders[MESA_SHADER_COMPUTE]->Program->nir);
    assert(nir && nir->info.workgroup_size[0]==256 && nir->info.workgroup_size[1]==1 && nir->info.workgroup_size[2]==1);
    NIR_PASS(_,nir,gl_nir_lower_buffers,program);
    NIR_PASS(_,nir,nir_lower_system_values);
    nir_lower_compute_system_values_options cs_options={};
    NIR_PASS(_,nir,nir_lower_compute_system_values,&cs_options);
    NIR_PASS(_,nir,ir3_nir_lower_io_gallium,true);
    ir3_shader_options shader_options={};
    shader_options.api_wavesize=IR3_DOUBLE_ONLY;
    shader_options.real_wavesize=IR3_SINGLE_OR_DOUBLE;
    ir3_finalize_nir(compiler,&shader_options.nir_options,nir);
    ir3_shader *shader=ir3_shader_from_nir(compiler,nir,&shader_options);assert(shader);
    ir3_shader_key key={};
    ir3_shader_variant *variant=ir3_shader_create_variant(shader,&key,true);
    if(!variant || !variant->bin)return nullptr;
    return variant;
}
#ifndef WAFFLE_GLSL_LIBRARY
int main(int argc,char **argv)
{
    if(argc!=5){std::fprintf(stderr,"usage: %s shader.comp shader.bin metadata.json disasm.txt\n",argv[0]);return 2;}
    ir3_shader_variant *variant=waffle_glsl_variant(argv[1]);if(!variant)return 3;
    FILE *binary=std::fopen(argv[2],"wb"),*metadata=std::fopen(argv[3],"w"),*disasm=std::fopen(argv[4],"w");assert(binary&&metadata&&disasm);
    assert(std::fwrite(variant->bin,1,variant->info.size,binary)==variant->info.size);
    std::fprintf(metadata,"{\n  \"source\": \"GLSL450 -> Mesa linkedNIR -> FD750 IR3\",\n  \"chip_id\": \"0x43051401\",\n  \"binary_bytes\": %u, \"constlen\": %u, \"private_bytes\": %u, \"shared_bytes\": %u,\n  \"local_size\": [%u,%u,%u], \"device_opened\": false, \"gpu_executed\": false\n}\n",variant->info.size,variant->constlen,variant->pvtmem_size,variant->shared_size,variant->local_size[0],variant->local_size[1],variant->local_size[2]);
    /* create_variant(write_disasm=true) captures disassembly before the
     * compiler destroys its temporary IR; calling disasm again dereferences
     * freed/null IR in ir3_shader.c. Preserve the compiler's own captured text. */
    assert(variant->disasm_info.disasm);
    std::fputs(variant->disasm_info.disasm,disasm);
    assert(!std::fclose(binary)&&!std::fclose(metadata)&&!std::fclose(disasm));

    return 0;
}

#endif
