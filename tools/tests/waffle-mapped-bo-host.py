"""Actual mapped-BO boundary + actual Mesa shim + actual Darwin client."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
parts={'__file__':str(root/'tools/tests/waffle-mesa-transport-host.py')};s=(root/'tools/tests/waffle-mesa-transport-host.py').read_text();exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],parts)
source=parts['source'].replace('*(unsigned *)v=11','*(unsigned *)v=12').replace('#define WAFFLE_MSM_PROBE','#define WAFFLE_MSM_MAP_PROBE\n#define WAFFLE_MSM_PROBE')
source=source.replace('static unsigned map_count,unmap_count;', 'static unsigned map_count,unmap_count,bulk_transfers;')
source=source.replace('static int copyin(uint64_t address,void *out,unsigned bytes){','static int copyin(uint64_t address,void *out,unsigned bytes){if(bytes==16384)bulk_transfers++;')
source=source.replace(' assert(copies==3 && reported==1', ' assert(map_count==11 && unmap_count==11 && !bulk_transfers);assert(copies==3 && reported==1')
source=source.replace(' assert(!msm_close(0,0,0,&owner));return 0;', '''
 struct waffle_msm_map mapreq={.handle=1,.bytes=16384};
 assert(!msm_ioctl(0,WAFFLE_MSM_MAP,(char *)&mapreq,0,&owner) && mapreq.address);
 uint64_t address=mapreq.address;mapreq.address=0;
 assert(msm_ioctl(0,WAFFLE_MSM_MAP,(char *)&mapreq,0,&owner)==EBUSY);
 mapreq.address=address+16384;assert(msm_ioctl(0,WAFFLE_MSM_UNMAP,(char *)&mapreq,0,&owner)==EINVAL);
 mapreq.address=address;assert(!msm_ioctl(0,WAFFLE_MSM_UNMAP,(char *)&mapreq,0,&owner));
 mapreq.address=0;mapreq.handle=3;assert(msm_ioctl(0,WAFFLE_MSM_MAP,(char *)&mapreq,0,&owner)==EINVAL);
 mapreq.handle=1;mapreq.bytes=4096;assert(msm_ioctl(0,WAFFLE_MSM_MAP,(char *)&mapreq,0,&owner)==EINVAL);
 assert(!msm_close(0,0,0,&owner));return 0;''')
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(source)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('Actual mapped BO client/shim/cdev:11 mappings/revokes,3jobs/768 checks/7negative tests, zero bulk transfer copies; map size/handle/duplicate/stale-address refusals; host only')
