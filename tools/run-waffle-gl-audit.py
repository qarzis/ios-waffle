"""Host-only real Mesa GL frontend over stock no-op MSM adapter; no GPU execution."""
from pathlib import Path
import argparse,os,json,subprocess
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--width',type=int,default=16);p.add_argument('--height',type=int,default=16);args=p.parse_args()
if not(1<=args.width<=2048 and 1<=args.height<=4096):p.error('Unsupported audit dimensions')
b=root/'work/waffle/gpu/mesa-gl-audit-build';out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
env=dict(os.environ,LD_PRELOAD=str(root/'work/waffle/gpu/waffle-msm-trace.so')+':'+str(b/'src/freedreno/drm-shim/libfreedreno_noop_drm_shim.so'),LD_LIBRARY_PATH=':'.join(str(b/x) for x in ['src/egl','src/gbm','src/mesa/glapi/es2api','src/mesa/glapi/shared-glapi']),GBM_BACKENDS_PATH=str(b/'src/gbm/backends/dri'),LIBGL_DRIVERS_PATH=str(b/'src/gallium/targets/dri'),MESA_LOADER_DRIVER_OVERRIDE='msm',FD_GPU_ID='750',DRM_SHIM_DEBUG='1',WAFFLE_MSM_TRACE=str(out/'msm-requests.jsonl'))
with (out/'frontend.log').open('w') as log:
 try:code=subprocess.run([str(root/'work/waffle/gpu/waffle-gl-context-audit'),str(args.width),str(args.height)],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=60).returncode
 except subprocess.TimeoutExpired:code='timeout60'
(out/'invocation.json').write_text(json.dumps({'host_only':True,'gpu_execution':False,'width':args.width,'height':args.height,'environment':{k:env[k] for k in ['LD_PRELOAD','LD_LIBRARY_PATH','GBM_BACKENDS_PATH','LIBGL_DRIVERS_PATH','MESA_LOADER_DRIVER_OVERRIDE','FD_GPU_ID','WAFFLE_MSM_TRACE']},'exit':code},indent=2)+'\n')
print('HOST ONLY frontend exit:',code);print((out/'frontend.log').read_text()[-4000:])
raise SystemExit(0 if code==0 else 1)
