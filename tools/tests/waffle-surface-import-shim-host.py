#!/usr/bin/env python3
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
ns={'__file__':str(root/'tools/tests/waffle-general-drm-host.py')}
s=(root/'tools/tests/waffle-general-drm-host.py').read_text();exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
code='#include <assert.h>\n#include <stdint.h>\n#include <stddef.h>\n'+ns['parts']['ioc']+ns['uapi']+ns['strip']((root/'tools/mesa/drm-shim/waffle_msm_transport.h').read_text())+r'''
int main(void){
 assert(waffle_msm_surface_request(0x7e,40,0,2)==WAFFLE_MSM_SURFACE_SAMPLE_IMPORT);
 assert(!waffle_msm_surface_request(0x7e,40,0,3));
 assert(waffle_msm_surface_request(0x7e,40,UINT32_MAX,2)==WAFFLE_MSM_SURFACE);
 assert(waffle_msm_surface_request(0x7e,40,0,1)==WAFFLE_MSM_SURFACE_IMPORT_TEST);
 assert(waffle_msm_surface_request(0x7e,40,0,0)==WAFFLE_MSM_SURFACE);
 assert(waffle_msm_surface_request(0x7e,40,UINT32_MAX,1)==WAFFLE_MSM_SURFACE);
 assert(waffle_msm_surface_request(0x7e,40,79,1)==WAFFLE_MSM_SURFACE);
 assert(!waffle_msm_surface_request(0x7e,39,0,1));
 assert(!waffle_msm_surface_request(0x7f,40,0,1));
 assert(waffle_msm_surface_request(0x43,sizeof(struct waffle_msm_gem_info),0,1)==WAFFLE_MSM_INFO);
}
'''
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS native surface shim: isolated explicit import redirect only, metadata/default/malformed/ordinary requests preserved; host only')
