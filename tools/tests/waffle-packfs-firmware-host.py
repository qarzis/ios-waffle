#!/usr/bin/env python3
"""Exercise appended metadata using actual kernel mount validation and FW lookup."""
import ctypes
import importlib.util
import mmap
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root/'tools'))
import mkpackfs as pf
spec = importlib.util.spec_from_file_location('graft', root/'tools/packfs-add-firmware.py')
graft = importlib.util.module_from_spec(spec); spec.loader.exec_module(graft)

def function(text, signature):
    start = text.index(signature); at = text.index('{', start); end = at+1; depth = 1
    while depth:
        depth += (text[end] == '{')-(text[end] == '}'); end += 1
    return text[start:end]

def main():
    with tempfile.TemporaryDirectory() as temp:
        t = Path(temp); tree = t/'tree'; tree.mkdir(); (tree/'dir').mkdir()
        (tree/'dir'/'compressed').write_bytes(b'compressible data'*14000)
        (tree/'raw').write_bytes(bytes(range(256))*20)
        (tree/'link').symlink_to('dir/compressed')
        fw = t/'fw'; fw.mkdir(); (fw/'adsp.mdt').write_bytes(b'ELF-test-metadata')
        (fw/'adsp.b01').write_bytes(bytes(range(256))*300)
        source = t/'source.packfs'; output = t/'result.packfs'
        node, _ = pf.scan(tree)
        pf.build_chunked(node, 4096, source, 1, raw_sources=[str(tree/'raw')])
        original = source.read_bytes(); report = graft.graft(source, fw, output)
        assert source.read_bytes() == original and report['original_extents_preserved']
        try: graft.graft(source, fw, output)
        except ValueError: pass
        else: raise AssertionError('overwrite accepted')
        try: graft.graft(output, fw, t/'duplicate.packfs')
        except ValueError: pass
        else: raise AssertionError('duplicate fw accepted')
        vfs = (root/'kernel/files/bsd/miscfs/packfs/packfs_vfsops.c').read_text()
        reader = (root/'kernel/files/bsd/dev/macan_firmware.c').read_text()
        code = '''
    #include <stdint.h>
    #include <stdbool.h>
    #include <stdlib.h>
    #include <string.h>
    #include <sys/stat.h>
    #include <sys/types.h>
    #include <errno.h>
    #include "packfs.h"
    #define MAXPATHLEN 1024
    struct packfs_mount {struct packfs_super pm_super; struct packfs_dnode *pm_nodes; char *pm_strings; const uint8_t *pm_membase;};
    typedef uintptr_t vm_offset_t;
    static const uint8_t *image; static uint64_t image_size;
    static dev_t mdevlookup(int disk) {return disk == 1 ? 1 : (dev_t)-1;}
    static int mdevgetkernelrange(dev_t dev, vm_offset_t *base, uint64_t *size) {*base=(uintptr_t)image;*size=image_size;return 0;}
    '''+function(vfs, 'static bool\npackfs_range_ok')+'\n'+function(vfs, 'static int\npackfs_validate')+'\n'+function(reader, 'static const struct packfs_dnode *\nimage_entry')+'\n'+function(reader, 'const uint8_t *\nmacan_image_file')+'''
    int validate(const uint8_t *bytes, uint64_t size) {
     image=bytes;image_size=size;
     struct packfs_mount pm={0};memcpy(&pm.pm_super,bytes,sizeof(pm.pm_super));
     pm.pm_nodes=(void *)(bytes+pm.pm_super.ps_nodes_off);pm.pm_strings=(void *)(bytes+pm.pm_super.ps_strings_off);pm.pm_membase=bytes;
     return packfs_validate(&pm);
    }
    int lookup(const char *name, const uint8_t *expected, uint64_t length) {
     uint64_t size=0;const uint8_t *p=macan_image_file("fw",name,&size);
     return p && size==length && memcmp(p,expected,size)==0;
    }
    '''
        (t/'check.c').write_text(code)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-I',str(root/'kernel/files/bsd/miscfs/packfs'),str(t/'check.c'),'-o',str(t/'check.so')],check=True)
        lib=ctypes.CDLL(str(t/'check.so')); lib.validate.argtypes=[ctypes.c_char_p,ctypes.c_uint64]
        lib.lookup.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_uint64]
        data=output.read_bytes(); assert lib.validate(data,len(data))==0
        for p in fw.iterdir(): assert lib.lookup(p.name.encode(),p.read_bytes(),p.stat().st_size)==1
        assert lib.lookup(b'missing',b'',0)==0
        for mutation in ('bad-parent','bad-chunk','bad-root'):
            damaged=bytearray(original); s,nodes,_,paths=graft.inspect(damaged)
            if mutation=='bad-parent': damaged[s[3]+pf.DNODE.size+32:s[3]+pf.DNODE.size+36]=(s[2]+1).to_bytes(4,'little')
            elif mutation=='bad-chunk':
                n=nodes[paths[b'/dir/compressed']]; damaged[n[5]:n[5]+4]=b'\0'*4
            else: damaged[0:8]=b'NOTPACK!'
            try: graft.inspect(damaged)
            except ValueError: pass
            else: raise AssertionError(mutation+' accepted')
    print('PASS: original extents and metadata preserved; actual kernel validator and raw firmware reader; overwrite/duplicate/malformed rejection')

if __name__ == '__main__': main()
