#ifndef WAFFLE_GPU_DATA_H
#define WAFFLE_GPU_DATA_H
#include "waffle_gpu_job.h"
#define WAFFLE_GPU_DATA_ADDRESS 0x8007c000u
#define WAFFLE_DATA_DESCRIPTOR_LO 1092u
#define WAFFLE_DATA_DESCRIPTOR_HI 1093u
static inline uint32_t waffle_data_word(const uint32_t *input,unsigned word,bool completed)
{
    if(word<256)return completed?input[word]:0xdead0000u+word;
    if(word<512)return input[word-256];
    return 0xdada0000u^word;
}
static inline uint32_t waffle_data_command_word(const uint32_t *input,unsigned fence,unsigned word,uint64_t va,bool completed)
{
    if(word==WAFFLE_DATA_DESCRIPTOR_LO)return (uint32_t)va;
    if(word==WAFFLE_DATA_DESCRIPTOR_HI)return (uint32_t)(va>>32);
    /* Old in-command BO SSBO bytes remain their initial contents. */
    if(word>=3072 && word<3584)return waffle_copy_initial(2,word);
    return waffle_job_word(input,fence,word,completed);
}
#endif
