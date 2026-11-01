"""Exercise the actual inner SMMU image guard across its bounded policy matrix."""
from pathlib import Path
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
s=(root/'kernel/files/bsd/dev/waffle_smmu.c').read_text();start=s.index('if(PE_parse_boot_argn("waffle_image"');end=s.index('if(PE_parse_boot_argn("waffle_ecats_access"',start)
condition=s[start:end];expr=condition[condition.index('        ('):condition.index(' {')].strip();assert expr.endswith(')');expr=expr[:-1]
c='''#include <stdbool.h>
#include <assert.h>
struct state {unsigned compute_image,compute_mode,dynamic_bo;};
int main(void){struct state value,*s=&value;
for(unsigned probe=93;probe<=94;probe++)for(unsigned image=1;image<=14;image++)for(unsigned compute=0;compute<=2;compute++)for(unsigned dyn=0;dyn<=1;dyn++){
*s=(struct state){image,compute,dyn};
bool refused='''+expr+''';
bool allowed=probe==94 && dyn==1 && image<=13 && (image==9?compute==1:image>=3?compute==2:compute==1 || compute==2);
assert(refused==!allowed);
}return 0;}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(c);subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(p/'test.c'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
print('Actual inner SMMU image guard:168 combinations modes1..14/compute0..2/dynamic0..1/probe93..94 passed')
