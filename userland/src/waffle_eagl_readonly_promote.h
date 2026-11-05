/* Private PID1-only candidate. A readonly import never becomes GPU writable.
 * Instead replace its texture storage with an owned upload before FBO attach.
 * Caller must abort the attachment on failure; ordinary UI admission unchanged. */
#ifndef GL_NO_ERROR
#define GL_NO_ERROR 0
#endif
#ifndef GL_UNPACK_SKIP_ROWS
#define GL_UNPACK_SKIP_ROWS 0x0cf3
#define GL_UNPACK_SKIP_PIXELS 0x0cf4
#endif
#ifndef GL_PIXEL_UNPACK_BUFFER
#define GL_PIXEL_UNPACK_BUFFER 0x88ec
#define GL_PIXEL_UNPACK_BUFFER_BINDING 0x88ef
#endif
static bool waffle_eagl_promote_readonly(struct eagl *e,struct image *image)
{
 (void)e;
 if(!image || !image->shared)return true;
 IOSurfaceRef surface=image->surface;
 if(getpid()!=1 || image->target || image->mirror || image->invert || image->alpha_first ||
    image->wrapped || image->to!=GL_TEXTURE_2D || image->format!=GL_BGRA ||
    image->type!=GL_UNSIGNED_BYTE || image->plane || image->width<=0 || image->height<=0 ||
    IOSurfaceGetPixelFormat(surface)!='BGRA' || IOSurfaceGetPlaneCount(surface) ||
    IOSurfaceGetBytesPerElement(surface)!=4 || (size_t)image->width!=IOSurfaceGetWidth(surface) ||
    (size_t)image->height!=IOSurfaceGetHeight(surface))return false;
 size_t row=IOSurfaceGetBytesPerRow(surface);
 if(row<(size_t)image->width*4 || row%4 || row/4>INT32_MAX)return false;
 if(IOSurfaceLock(surface,kIOSurfaceLockReadOnly,NULL)!=KERN_SUCCESS)return false;
 const void *base=IOSurfaceGetBaseAddress(surface);
 GLint bound=0,length=0,alignment=0,skip_rows=0,skip_pixels=0,buffer=0;
 bool ok=false;
 if(!base || glGetError()!=GL_NO_ERROR)goto unlock;
 glGetIntegerv(GL_TEXTURE_BINDING_2D,&bound);
 glGetIntegerv(GL_UNPACK_ROW_LENGTH,&length);glGetIntegerv(GL_UNPACK_ALIGNMENT,&alignment);
 glGetIntegerv(GL_UNPACK_SKIP_ROWS,&skip_rows);glGetIntegerv(GL_UNPACK_SKIP_PIXELS,&skip_pixels);
 glGetIntegerv(GL_PIXEL_UNPACK_BUFFER_BINDING,&buffer);
 glBindTexture(GL_TEXTURE_2D,image->texture);
 glBindBuffer(GL_PIXEL_UNPACK_BUFFER,0);
 glPixelStorei(GL_UNPACK_SKIP_ROWS,0);glPixelStorei(GL_UNPACK_SKIP_PIXELS,0);
 glPixelStorei(GL_UNPACK_ROW_LENGTH,(GLint)(row/4));glPixelStorei(GL_UNPACK_ALIGNMENT,1);
 glTexImage2D(GL_TEXTURE_2D,0,(GLint)internal_format(image->internal,image->format),
     image->width,image->height,0,image->format,image->type,base);
 ok=glGetError()==GL_NO_ERROR;
 glBindTexture(GL_TEXTURE_2D,(GLuint)bound);
 glPixelStorei(GL_UNPACK_ROW_LENGTH,length);glPixelStorei(GL_UNPACK_ALIGNMENT,alignment);
 glPixelStorei(GL_UNPACK_SKIP_ROWS,skip_rows);glPixelStorei(GL_UNPACK_SKIP_PIXELS,skip_pixels);
 glBindBuffer(GL_PIXEL_UNPACK_BUFFER,(GLuint)buffer);
 if(glGetError()!=GL_NO_ERROR)ok=false;
unlock:
 if(IOSurfaceUnlock(surface,kIOSurfaceLockReadOnly,NULL)!=KERN_SUCCESS)ok=false;
 if(ok){image->shared=false;image->seed=IOSurfaceGetSeed(surface);}
 say("waffle-readonly-promote: passed=%u texture=%u sid=%u owned_upload=1 native_GPU_writes=0\n",
     ok,image->texture,IOSurfaceGetID(surface));
 return ok;
}
