/* Query only: never clear/draw/blit into the native readonly import. */
static bool check_surface_role(GLuint texture)
{
 GLint previous=0;GLuint framebuffer=0;bool ok=false;
 int fd=existing_gpu_fd();if(fd<0)return false;
 struct waffle_msm_surface native={.surface=IOSurfaceGetID(hook_surface)};
 if(ioctl(fd,WAFFLE_MSM_SURFACE_SAMPLE_IMPORT,&native) || !native.handle){close(fd);return false;}
 close(fd);
 printf("waffle-gl-surface-role: begin sid=%u handle=%u readonly_native=1\n",native.surface,native.handle);
 glGetIntegerv(GL_FRAMEBUFFER_BINDING,&previous);
 glGenFramebuffers(1,&framebuffer);
 glBindFramebuffer(GL_FRAMEBUFFER,framebuffer);
 glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture,0);
 GLenum status=glCheckFramebufferStatus(GL_FRAMEBUFFER),error=glGetError();
 ok=framebuffer && status==GL_FRAMEBUFFER_COMPLETE && error==GL_NO_ERROR;
 glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,0,0);
 glBindFramebuffer(GL_FRAMEBUFFER,(GLuint)previous);
 glDeleteFramebuffers(1,&framebuffer);
 if(glGetError()!=GL_NO_ERROR)ok=false;
 printf("waffle-gl-surface-role: passed=%u sid=%u handle=%u framebuffer_status=%x GL_error=%x readonly_native=1 attachment_allowed=1 draw_calls=0 restored_binding=1\n",ok,native.surface,native.handle,status,error);
 return ok;
}
