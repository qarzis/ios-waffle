/* Actual EAGL FBO attachment promotes only to owned storage. GPU never writes
 * the native import; ordinary target readback publishes the resulting pixels. */
static bool check_surface_promotion(GLuint texture,GLuint sibling)
{
 const unsigned width=750,height=1624;size_t row=IOSurfaceGetBytesPerRow(hook_surface),bytes=row*height;
 uint8_t *saved=malloc(bytes);uint32_t *pixels=malloc((size_t)width*height*4);
 bool saved_valid=false,restored=false,ok=false;
 GLint old_texture=0,old_read=0,old_draw=0,old_pack=0,old_row=0;
 GLboolean old_mask[4]={0},old_scissor=GL_FALSE;GLfloat old_clear[4]={0};
 GLuint framebuffer=0;unsigned wrong=0,native_wrong=0,sibling_wrong=0;
 glGetIntegerv(GL_TEXTURE_BINDING_2D,&old_texture);
 glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING,&old_read);glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING,&old_draw);
 glGetIntegerv(GL_PACK_ALIGNMENT,&old_pack);glGetIntegerv(GL_PACK_ROW_LENGTH,&old_row);
 glGetBooleanv(GL_COLOR_WRITEMASK,old_mask);glGetFloatv(GL_COLOR_CLEAR_VALUE,old_clear);old_scissor=glIsEnabled(GL_SCISSOR_TEST);
 if(!saved || !pixels || row<width*4 || glGetError()!=GL_NO_ERROR)goto done;
 /* First publish any preceding target draw before taking the CPU baseline. */
 glFinish();
 if(glGetError()!=GL_NO_ERROR || IOSurfaceLock(hook_surface,kIOSurfaceLockReadOnly,NULL)!=KERN_SUCCESS)goto done;
 memcpy(saved,IOSurfaceGetBaseAddress(hook_surface),bytes);saved_valid=true;
 if(IOSurfaceUnlock(hook_surface,kIOSurfaceLockReadOnly,NULL)!=KERN_SUCCESS)goto done;
 printf("waffle-gl-surface-promotion: begin texture=%u sibling=%u sid=%u native_readonly=1\n",texture,sibling,IOSurfaceGetID(hook_surface));
 glGenFramebuffers(1,&framebuffer);glBindFramebuffer(GL_FRAMEBUFFER,framebuffer);
 /* No TexImage call in this test: the actual EAGL attachment must promote. */
 glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture,0);
 if(!framebuffer || glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE || glGetError()!=GL_NO_ERROR)goto done;
 glDisable(GL_SCISSOR_TEST);glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);
 glClearColor(0,1,0,1);glClear(GL_COLOR_BUFFER_BIT);
 glPixelStorei(GL_PACK_ALIGNMENT,4);glPixelStorei(GL_PACK_ROW_LENGTH,0);
 glReadPixels(0,0,width,height,GL_RGBA,GL_UNSIGNED_BYTE,pixels);
 if(glGetError()!=GL_NO_ERROR)goto done;
 for(size_t i=0;i<(size_t)width*height;i++)if(pixels[i]!=0xff00ff00u)wrong++;
 if(wrong)goto done;
 /* Complete ordinary target readback into IOSurface before CPU inspection. */
 glFinish();
 if(glGetError()!=GL_NO_ERROR || IOSurfaceLock(hook_surface,kIOSurfaceLockReadOnly,NULL)!=KERN_SUCCESS)goto done;
 const uint8_t *base=IOSurfaceGetBaseAddress(hook_surface);
 for(unsigned y=0;y<height;y++)for(unsigned x=0;x<width;x++){
  uint32_t pixel;memcpy(&pixel,base+y*row+x*4,4);if(pixel!=0xff00ff00u)native_wrong++;
 }
 if(IOSurfaceUnlock(hook_surface,kIOSurfaceLockReadOnly,NULL)!=KERN_SUCCESS || native_wrong)goto done;
 printf("waffle-gl-surface-promotion: native_checked=1218000 wrong=0 before_sibling=1\n");
 struct waffle_surface_sample_result result;
 if(!waffle_gl_sample_texture(sibling,base,row,width,height,&result))goto done;
 sibling_wrong=result.wrong;
 printf("waffle-gl-surface-promotion: sibling_checked=256 wrong=%u native_cache_sync=1\n",sibling_wrong);
 ok=sibling_wrong==0;
done:
 if(saved_valid && IOSurfaceLock(hook_surface,0,NULL)==KERN_SUCCESS){
  memcpy(IOSurfaceGetBaseAddress(hook_surface),saved,bytes);
  restored=IOSurfaceUnlock(hook_surface,0,NULL)==KERN_SUCCESS;
 }
 if(framebuffer)glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,0,0);
 glBindFramebuffer(GL_READ_FRAMEBUFFER,(GLuint)old_read);glBindFramebuffer(GL_DRAW_FRAMEBUFFER,(GLuint)old_draw);
 glBindTexture(GL_TEXTURE_2D,(GLuint)old_texture);
 glPixelStorei(GL_PACK_ALIGNMENT,old_pack);glPixelStorei(GL_PACK_ROW_LENGTH,old_row);
 glColorMask(old_mask[0],old_mask[1],old_mask[2],old_mask[3]);glClearColor(old_clear[0],old_clear[1],old_clear[2],old_clear[3]);
 if(old_scissor)glEnable(GL_SCISSOR_TEST);else glDisable(GL_SCISSOR_TEST);
 if(framebuffer)glDeleteFramebuffers(1,&framebuffer);
 if(glGetError()!=GL_NO_ERROR)ok=false;
 ok=ok&&restored;
 printf("waffle-gl-surface-promotion: passed=%u texture=%u owned_wrong=%u native_wrong=%u sibling_wrong=%u restored=%u pixels=1218000\n",ok,texture,wrong,native_wrong,sibling_wrong,restored);
 free(saved);free(pixels);return ok;
}
