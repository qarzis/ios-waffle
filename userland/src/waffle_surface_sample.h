#ifndef WAFFLE_SURFACE_SAMPLE_H
#define WAFFLE_SURFACE_SAMPLE_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
struct waffle_surface_sample_result {uint32_t pixels[256],expected[256];unsigned wrong,error,stage;};
bool waffle_gl_sample_texture(unsigned texture,const uint8_t *source,size_t stride,unsigned width,unsigned height,struct waffle_surface_sample_result *result);
#endif
