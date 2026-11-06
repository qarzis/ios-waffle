"""Bind actual DeviceInfo dispatch to captured board and pinned KGSL policy."""
from pathlib import Path
import runpy,hashlib,json,re,subprocess,tempfile,struct
root=Path(__file__).resolve().parents[2];u=root.parent/'unixnu-reference';dt=root/'work/waffle/gpu/android-capture2/android-live.dtb'
nodes=runpy.run_path(str(root/'tools/check-waffle-dtb.py'))['parse_fdt'](dt.read_bytes());gpu=nodes['/soc/qcom,kgsl-3d0@3d00000']
chip=struct.unpack('>I',gpu['qcom,chipid'])[0];ubwc=struct.unpack('>I',gpu['qcom,ubwc-mode'])[0];ddr=struct.unpack('>I',nodes['/memory']['ddr_device_type'])[0]
assert chip==0x43051401 and ubwc==4 and ddr==8
core=root/'work/waffle/gpu/vendor/adreno-gpulist.h';text=core.read_text().split('adreno_gpu_core_gen7_9_1 = {',1)[1].split('\n};',1)[0];bank=int(re.search(r'\.highest_bank_bit\s*=\s*(\d+)',text)[1]);assert bank==16 and ddr!=7
mesa=u/'.cache/mesa-work/src/freedreno/vulkan/tu_knl_kgsl.cc';text=mesa.read_text();begin=text.index('   switch (ubwc_version)');end=text.index('   /* kgsl unfortunately',begin);policy=text[begin:end]
header=(mesa.parent/'msm_kgsl.h').read_text();defines='\n'.join(re.findall(r'^#define KGSL_UBWC_[1-6]_0.*$',header,re.M))
code='''#include <cstdio>
enum {FDL_MACROTILE_4_CHANNEL,FDL_MACROTILE_8_CHANNEL,VK_ERROR_INITIALIZATION_FAILED=-1};
struct Device {struct {unsigned bank_swizzle_levels,macrotile_mode;} ubwc_config;};
int vk_errorf(int,int,const char*,...){return -1;}
int main(){Device storage{};Device *device=&storage;int instance=0;unsigned ubwc_version=4;
'''+defines+'\n'+policy+'''std::printf("%u %u",device->ubwc_config.bank_swizzle_levels,device->ubwc_config.macrotile_mode);return 0;}
'''
ns={'__file__':str(root/'tools/tests/waffle-general-drm-host.py')};s=(root/'tools/tests/waffle-general-drm-host.py').read_text();exec(s[:s.index('\nwith tempfile.TemporaryDirectory()')],ns)
t=r'''
int main(void){assert(!drm_open(0,0,0,&owner));struct waffle_unixnu_call c={.version=2,.method=15,.output_bytes=sizeof(struct waffle_unixnu_device_info)};assert(!drm_ioctl(0,WAFFLE_UNIXNU_CALL,(char*)&c,0,&owner));struct waffle_unixnu_device_info d;memcpy(&d,c.payload,sizeof(d));printf("%u %u %u %u %u %u %u %llu %llu",d.chip_id,d.gmem_bytes,d.highest_bank_bit,d.ubwc_swizzle,d.macrotile_mode,d.ubwc_version,d.flags,(unsigned long long)d.va_start,(unsigned long long)d.va_size);c.output_bytes--;assert(drm_ioctl(0,WAFFLE_UNIXNU_CALL,(char*)&c,0,&owner)==EINVAL);assert(!drm_close(0,0,0,&owner));return 0;}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'policy.cpp').write_text(code);subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror',str(p/'policy.cpp'),'-o',str(p/'policy')],check=True);swizzle,macro=map(int,subprocess.check_output([str(p/'policy')],text=True).split());assert (swizzle,macro)==(6,1)
 (p/'backend.c').write_text(ns['h']+ns['parts']['ioc']+ns['uapi']+ns['source']+t)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-misleading-indentation','-fsanitize=address,undefined','-I',str(root/'kernel/files/bsd/sys'),str(p/'backend.c'),'-o',str(p/'backend')],check=True)
 actual=list(map(int,subprocess.check_output([str(p/'backend')],text=True).split()));assert actual==[chip,3145728,bank,swizzle,macro,ubwc,1,0x100000000,268435456],actual
record={'hardware_tested':False,'captured_board':'PJD110 SM8650','chip_id':hex(chip),'ddr_device_type':ddr,'highest_bank_bit':bank,'ubwc_version':ubwc,'ubwc_swizzle':swizzle,'macrotile_mode':macro,'macrotile_channels':8,'evidence':{str(p.relative_to(root)) if p.is_relative_to(root) else str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [dt,core,mesa]},'policy':'actual pinned KGSL UBWC switch compiled; DDR4-only bank override excluded by captured DDR type8'}
(root/'work/waffle/unixnu-audit/PJD110_DEVICE_INFO.json').write_text(json.dumps(record,indent=2)+'\n')
print('PASS actual DeviceInfo dispatch vs captured chip/UBWC4/DDR8, native core bank16 and compiled Mesa KGSL swizzle6/eight-channel policy; exact ABI shape and wrong output size refusal; host only')
