/* Generated from existing eagl_slots.txt and pinned Mesa gl.xml. */
static void **waffle_hook_table;
static void waffle_hook_glAttachShader(GLuint program, GLuint shader) { ((void (*)(void *, GLuint, GLuint))waffle_hook_table[599])(waffle_hook_table[0], program, shader); }
#define glAttachShader waffle_hook_glAttachShader
static void waffle_hook_glBindBuffer(GLenum target, GLuint buffer) { ((void (*)(void *, GLenum, GLuint))waffle_hook_table[643])(waffle_hook_table[0], target, buffer); }
#define glBindBuffer waffle_hook_glBindBuffer
static void waffle_hook_glBindFramebuffer(GLenum target, GLuint framebuffer) { ((void (*)(void *, GLenum, GLuint))waffle_hook_table[673])(waffle_hook_table[0], target, framebuffer); }
#define glBindFramebuffer waffle_hook_glBindFramebuffer
static void waffle_hook_glBindTexture(GLenum target, GLuint texture) { ((void (*)(void *, GLenum, GLuint))waffle_hook_table[6])(waffle_hook_table[0], target, texture); }
#define glBindTexture waffle_hook_glBindTexture
static void waffle_hook_glBindVertexArray(GLuint array) { ((void (*)(void *, GLuint))waffle_hook_table[769])(waffle_hook_table[0], array); }
#define glBindVertexArray waffle_hook_glBindVertexArray
static void waffle_hook_glBufferData(GLenum target, GLsizeiptr size, const void *data, GLenum usage) { ((void (*)(void *, GLenum, GLsizeiptr, const void *, GLenum))waffle_hook_table[647])(waffle_hook_table[0], target, size, data, usage); }
#define glBufferData waffle_hook_glBufferData
static GLenum waffle_hook_glCheckFramebufferStatus(GLenum target) { return ((GLenum (*)(void *, GLenum))waffle_hook_table[676])(waffle_hook_table[0], target); }
#define glCheckFramebufferStatus waffle_hook_glCheckFramebufferStatus
static void waffle_hook_glClear(GLbitfield mask) { ((void (*)(void *, GLbitfield))waffle_hook_table[11])(waffle_hook_table[0], mask); }
#define glClear waffle_hook_glClear
static void waffle_hook_glClearColor(GLfloat red, GLfloat green, GLfloat blue, GLfloat alpha) { ((void (*)(void *, GLfloat, GLfloat, GLfloat, GLfloat))waffle_hook_table[13])(waffle_hook_table[0], red, green, blue, alpha); }
#define glClearColor waffle_hook_glClearColor
static void waffle_hook_glCompileShader(GLuint shader) { ((void (*)(void *, GLuint))waffle_hook_table[597])(waffle_hook_table[0], shader); }
#define glCompileShader waffle_hook_glCompileShader
static GLuint waffle_hook_glCreateProgram(void) { return ((GLuint (*)(void *))waffle_hook_table[598])(waffle_hook_table[0]); }
#define glCreateProgram waffle_hook_glCreateProgram
static GLuint waffle_hook_glCreateShader(GLenum type) { return ((GLuint (*)(void *, GLenum))waffle_hook_table[595])(waffle_hook_table[0], type); }
#define glCreateShader waffle_hook_glCreateShader
static void waffle_hook_glDeleteBuffers(GLsizei n, const GLuint *buffers) { ((void (*)(void *, GLsizei, const GLuint *))waffle_hook_table[644])(waffle_hook_table[0], n, buffers); }
#define glDeleteBuffers waffle_hook_glDeleteBuffers
static void waffle_hook_glDeleteFramebuffers(GLsizei n, const GLuint *framebuffers) { ((void (*)(void *, GLsizei, const GLuint *))waffle_hook_table[674])(waffle_hook_table[0], n, framebuffers); }
#define glDeleteFramebuffers waffle_hook_glDeleteFramebuffers
static void waffle_hook_glDeleteProgram(GLuint program) { ((void (*)(void *, GLuint))waffle_hook_table[592])(waffle_hook_table[0], program); }
#define glDeleteProgram waffle_hook_glDeleteProgram
static void waffle_hook_glDeleteShader(GLuint shader) { ((void (*)(void *, GLuint))waffle_hook_table[592])(waffle_hook_table[0], shader); }
#define glDeleteShader waffle_hook_glDeleteShader
static void waffle_hook_glDeleteTextures(GLsizei n, const GLuint *textures) { ((void (*)(void *, GLsizei, const GLuint *))waffle_hook_table[60])(waffle_hook_table[0], n, textures); }
#define glDeleteTextures waffle_hook_glDeleteTextures
static void waffle_hook_glDeleteVertexArrays(GLsizei n, const GLuint *arrays) { ((void (*)(void *, GLsizei, const GLuint *))waffle_hook_table[770])(waffle_hook_table[0], n, arrays); }
#define glDeleteVertexArrays waffle_hook_glDeleteVertexArrays
static void waffle_hook_glDisable(GLenum cap) { ((void (*)(void *, GLenum))waffle_hook_table[64])(waffle_hook_table[0], cap); }
#define glDisable waffle_hook_glDisable
static void waffle_hook_glDrawArrays(GLenum mode, GLint first, GLsizei count) { ((void (*)(void *, GLenum, GLint, GLsizei))waffle_hook_table[66])(waffle_hook_table[0], mode, first, count); }
#define glDrawArrays waffle_hook_glDrawArrays
static void waffle_hook_glEnableVertexAttribArray(GLuint index) { ((void (*)(void *, GLuint))waffle_hook_table[513])(waffle_hook_table[0], index); }
#define glEnableVertexAttribArray waffle_hook_glEnableVertexAttribArray
static void waffle_hook_glFinish(void) { ((void (*)(void *))waffle_hook_table[90])(waffle_hook_table[0]); }
#define glFinish waffle_hook_glFinish
static void waffle_hook_glFramebufferTexture2D(GLenum target, GLenum attachment, GLenum textarget, GLuint texture, GLint level) { ((void (*)(void *, GLenum, GLenum, GLenum, GLuint, GLint))waffle_hook_table[678])(waffle_hook_table[0], target, attachment, textarget, texture, level); }
#define glFramebufferTexture2D waffle_hook_glFramebufferTexture2D
static void waffle_hook_glGenBuffers(GLsizei n, GLuint *buffers) { ((void (*)(void *, GLsizei, GLuint *))waffle_hook_table[645])(waffle_hook_table[0], n, buffers); }
#define glGenBuffers waffle_hook_glGenBuffers
static void waffle_hook_glGenFramebuffers(GLsizei n, GLuint *framebuffers) { ((void (*)(void *, GLsizei, GLuint *))waffle_hook_table[675])(waffle_hook_table[0], n, framebuffers); }
#define glGenFramebuffers waffle_hook_glGenFramebuffers
static void waffle_hook_glGenTextures(GLsizei n, GLuint *textures) { ((void (*)(void *, GLsizei, GLuint *))waffle_hook_table[99])(waffle_hook_table[0], n, textures); }
#define glGenTextures waffle_hook_glGenTextures
static void waffle_hook_glGenVertexArrays(GLsizei n, GLuint *arrays) { ((void (*)(void *, GLsizei, GLuint *))waffle_hook_table[771])(waffle_hook_table[0], n, arrays); }
#define glGenVertexArrays waffle_hook_glGenVertexArrays
static GLint waffle_hook_glGetAttribLocation(GLuint program, const GLchar *name) { return ((GLint (*)(void *, GLuint, const GLchar *))waffle_hook_table[633])(waffle_hook_table[0], program, name); }
#define glGetAttribLocation waffle_hook_glGetAttribLocation
static GLenum waffle_hook_glGetError(void) { return ((GLenum (*)(void *))waffle_hook_table[103])(waffle_hook_table[0]); }
#define glGetError waffle_hook_glGetError
static void waffle_hook_glGetProgramiv(GLuint program, GLenum pname, GLint *params) { ((void (*)(void *, GLuint, GLenum, GLint *))waffle_hook_table[659])(waffle_hook_table[0], program, pname, params); }
#define glGetProgramiv waffle_hook_glGetProgramiv
static void waffle_hook_glGetShaderInfoLog(GLuint shader, GLsizei bufSize, GLsizei *length, GLchar *infoLog) { ((void (*)(void *, GLuint, GLsizei, GLsizei *, GLchar *))waffle_hook_table[660])(waffle_hook_table[0], shader, bufSize, length, infoLog); }
#define glGetShaderInfoLog waffle_hook_glGetShaderInfoLog
static void waffle_hook_glGetShaderiv(GLuint shader, GLenum pname, GLint *params) { ((void (*)(void *, GLuint, GLenum, GLint *))waffle_hook_table[658])(waffle_hook_table[0], shader, pname, params); }
#define glGetShaderiv waffle_hook_glGetShaderiv
static const GLubyte * waffle_hook_glGetString(GLenum name) { return ((const GLubyte * (*)(void *, GLenum))waffle_hook_table[118])(waffle_hook_table[0], name); }
#define glGetString waffle_hook_glGetString
static void waffle_hook_glLinkProgram(GLuint program) { ((void (*)(void *, GLuint))waffle_hook_table[600])(waffle_hook_table[0], program); }
#define glLinkProgram waffle_hook_glLinkProgram
static void waffle_hook_glPixelStorei(GLenum pname, GLint param) { ((void (*)(void *, GLenum, GLint))waffle_hook_table[196])(waffle_hook_table[0], pname, param); }
#define glPixelStorei waffle_hook_glPixelStorei
static void waffle_hook_glReadPixels(GLint x, GLint y, GLsizei width, GLsizei height, GLenum format, GLenum type, void *pixels) { ((void (*)(void *, GLint, GLint, GLsizei, GLsizei, GLenum, GLenum, void *))waffle_hook_table[238])(waffle_hook_table[0], x, y, width, height, format, type, pixels); }
#define glReadPixels waffle_hook_glReadPixels
static void waffle_hook_glShaderSource(GLuint shader, GLsizei count, const GLchar *const*string, const GLint *length) { ((void (*)(void *, GLuint, GLsizei, const GLchar *const*, const GLint *))waffle_hook_table[596])(waffle_hook_table[0], shader, count, string, length); }
#define glShaderSource waffle_hook_glShaderSource
static void waffle_hook_glTexImage2D(GLenum target, GLint level, GLint internalformat, GLsizei width, GLsizei height, GLint border, GLenum format, GLenum type, const void *pixels) { ((void (*)(void *, GLenum, GLint, GLint, GLsizei, GLsizei, GLint, GLenum, GLenum, const void *))waffle_hook_table[302])(waffle_hook_table[0], target, level, internalformat, width, height, border, format, type, pixels); }
#define glTexImage2D waffle_hook_glTexImage2D
static void waffle_hook_glTexParameteri(GLenum target, GLenum pname, GLint param) { ((void (*)(void *, GLenum, GLenum, GLint))waffle_hook_table[305])(waffle_hook_table[0], target, pname, param); }
#define glTexParameteri waffle_hook_glTexParameteri
static void waffle_hook_glUseProgram(GLuint program) { ((void (*)(void *, GLuint))waffle_hook_table[601])(waffle_hook_table[0], program); }
#define glUseProgram waffle_hook_glUseProgram
static void waffle_hook_glVertexAttribPointer(GLuint index, GLint size, GLenum type, GLboolean normalized, GLsizei stride, const void *pointer) { ((void (*)(void *, GLuint, GLint, GLenum, GLboolean, GLsizei, const void *))waffle_hook_table[512])(waffle_hook_table[0], index, size, type, normalized, stride, pointer); }
#define glVertexAttribPointer waffle_hook_glVertexAttribPointer
static void waffle_hook_glViewport(GLint x, GLint y, GLsizei width, GLsizei height) { ((void (*)(void *, GLint, GLint, GLsizei, GLsizei))waffle_hook_table[336])(waffle_hook_table[0], x, y, width, height); }
#define glViewport waffle_hook_glViewport
