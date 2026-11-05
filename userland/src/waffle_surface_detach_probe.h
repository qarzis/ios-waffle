/* Isolated storage replacement: never render until TexImage succeeds.
 * The other texture still retains the native readonly source throughout. */
static bool check_surface_detach(GLuint texture)
{
 GLint old_texture=0,old_read=0,old_draw=0,old_pack=0,old_row=0;GLuint framebuffer=0;bool ok=false;
 GLboolean old_mask[4]={0},old_scissor=GL_FALSE;GLfloat old_clear[4]={0};
 uint32_t *pixels=NULL;GLenum status=0,error=0;unsigned wrong=0;
 const unsigned width=750,height=1624;size_t bytes=(size_t)width*height*4;
 glGetIntegerv(GL_TEXTURE_BINDING_2D,&old_texture);
 glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING,&old_read);
 glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING,&old_draw);
 glGetIntegerv(GL_PACK_ALIGNMENT,&old_pack);glGetIntegerv(GL_PACK_ROW_LENGTH,&old_row);
 glGetBooleanv(GL_COLOR_WRITEMASK,old_mask);glGetFloatv(GL_COLOR_CLEAR_VALUE,old_clear);
 old_scissor=glIsEnabled(GL_SCISSOR_TEST);
 if(glGetError()!=GL_NO_ERROR)return false;
 pixels=malloc(bytes);if(!pixels)return false;
 memset(pixels,0x5a,bytes);
 printf("waffle-gl-surface-detach: begin texture=%u sid=%u readonly_native=1\n",texture,IOSurfaceGetID(hook_surface));
 glBindTexture(GL_TEXTURE_2D,texture);
 /* Per EGLImage sibling semantics this respecifies only this texture. */
 glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,width,height,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
 error=glGetError();if(error!=GL_NO_ERROR)goto done;
 printf("waffle-gl-surface-detach: replaced=1 texture=%u error=0 before_draw=1\n",texture);
 glGenFramebuffers(1,&framebuffer);
 glBindFramebuffer(GL_FRAMEBUFFER,framebuffer);
 glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture,0);
 status=glCheckFramebufferStatus(GL_FRAMEBUFFER);error=glGetError();
 if(!framebuffer || status!=GL_FRAMEBUFFER_COMPLETE || error!=GL_NO_ERROR)goto done;
 glDisable(GL_SCISSOR_TEST);glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);
 glClearColor(0,1,0,1);glClear(GL_COLOR_BUFFER_BIT);
 /* EAGL defers clears; materialize before the passthrough readback. */
 glFinish();
 glPixelStorei(GL_PACK_ALIGNMENT,4);glPixelStorei(GL_PACK_ROW_LENGTH,0);
 glReadPixels(0,0,width,height,GL_RGBA,GL_UNSIGNED_BYTE,pixels);
 error=glGetError();if(error!=GL_NO_ERROR)goto done;
 for(size_t i=0;i<(size_t)width*height;i++)if(pixels[i]!=0xff00ff00u)wrong++;
 ok=wrong==0;
done:
 if(framebuffer){glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,0,0);}
 glBindFramebuffer(GL_READ_FRAMEBUFFER,(GLuint)old_read);
 glBindFramebuffer(GL_DRAW_FRAMEBUFFER,(GLuint)old_draw);
 glPixelStorei(GL_PACK_ALIGNMENT,old_pack);glPixelStorei(GL_PACK_ROW_LENGTH,old_row);
 glColorMask(old_mask[0],old_mask[1],old_mask[2],old_mask[3]);
 glClearColor(old_clear[0],old_clear[1],old_clear[2],old_clear[3]);
 if(old_scissor)glEnable(GL_SCISSOR_TEST);else glDisable(GL_SCISSOR_TEST);
 glBindTexture(GL_TEXTURE_2D,(GLuint)old_texture);
 if(framebuffer)glDeleteFramebuffers(1,&framebuffer);
 free(pixels);
 if(glGetError()!=GL_NO_ERROR)ok=false;
 printf("waffle-gl-surface-detach: passed=%u texture=%u checked=%u wrong=%u status=%x error=%x owned_write=1 sibling_retained=1 flush_before_read=1\n",ok,texture,ok?width*height:0,wrong,status,error);
 return ok;
}
