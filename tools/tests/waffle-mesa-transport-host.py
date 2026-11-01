"""Actual Mesa DRM shim, actual diagnostic client and actual cdev, with GPU model."""
from pathlib import Path
import subprocess,tempfile,re
root=Path(__file__).resolve().parents[2]
parts={'__file__':str(root/'tools/tests/waffle-msm-host.py')};s=(root/'tools/tests/waffle-msm-host.py').read_text();exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],parts)
shim=re.sub(r'^#include .*$','',(root/'tools/mesa/drm-shim/drm_shim.c').read_text(),flags=re.M)
client=parts['client']
# Distinct C translation units have separate static call symbols in production.
source=parts['h']+'\n'+parts['parts']['ioc']+'\n'+parts['uapi']+'\n#include "waffle_gpu_data.h"\n'+parts['source']+parts['mini']+'\n#define WAFFLE_MSM_PROBE\n#define call mesa_transport_call\n'+shim+'\n#undef call\n'+client+parts['test'].replace(' assert(waffle_gpu_msm_register());', ''' assert(drmOpenWithType("msm",NULL,2)==-1 && errno==22);
 struct waffle_msm_gem_new invalid={.size=16384};
 assert(drmCommandWriteRead(3,2,&invalid,1)==-22 && !copies);
 assert(drmCommandWriteRead(3,0,&invalid,sizeof(invalid))==-38 && !copies);
 assert(waffle_gpu_msm_register());''')
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(source)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('Actual Mesa drm_shim + actual user + actual cdev: commandWriteRead/commandWrite/ioctl, 3 jobs/768 checks/7 negatives; unsupported genericmsm/name/size refused; host only')
