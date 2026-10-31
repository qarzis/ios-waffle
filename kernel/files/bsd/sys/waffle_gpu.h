#ifndef WAFFLE_GPU_H
#define WAFFLE_GPU_H
#include <stdbool.h>
/* PJD110 live FDT, pinned OnePlus Gen7.9.1 definitions and SM8650 GPUCC.
 * GPU GMU register identifiers in gen7_reg.h are DWORD indices relative
 * to 0x03d00000, not offsets relative to the GMU mapping at 0x03d68000.
 */
#define WAFFLE_GPU_CHIP_ID       0x43051401u
#define WAFFLE_GPU_GMEM_SIZE     0x00300000u
#define WAFFLE_GCC_BASE          0x00100000u
#define WAFFLE_GCC_SIZE          0x001f4200u
#define WAFFLE_GPU_CFG_AHB       0x71004u
#define WAFFLE_GPU_MEMNOC        0x71010u
#define WAFFLE_GPU_DDR_AXI       0x71154u
#define WAFFLE_GPU_SNOC          0x71018u
#define WAFFLE_GPUCC_BASE        0x03d90000u
#define WAFFLE_GPUCC_SIZE        0x00009800u
#define WAFFLE_GPU_CX_GDSCR      0x9108u
#define WAFFLE_GPU_CX_HW_CTRL    0x9168u
#define WAFFLE_GPU_GX_GDSCR      0x905cu
#define WAFFLE_GPU_AHB           0x911cu
#define WAFFLE_GPU_CX_GMU        0x913cu
#define WAFFLE_GPU_CXO_AON       0x9004u
#define WAFFLE_GPU_DEMET         0x900cu
#define WAFFLE_GPU_CXO           0x9144u
#define WAFFLE_GPU_HUB_AON       0x93e8u
#define WAFFLE_GPU_HUB_CX_INT    0x9148u
#define WAFFLE_GPU_SMMU_CLOCK    0x7000u
#define WAFFLE_GPU_PLL_VOTE      0x52000u
#define WAFFLE_GPU_PLL_MASK      ((1u << 15) | (1u << 16))
#define WAFFLE_GPU_GMU_RCGR      0x9318u
#define WAFFLE_GPU_HUB_RCGR      0x93ecu
#define WAFFLE_GPU_BASE          0x03d00000u
#define WAFFLE_GPU_SIZE          0x00040000u
#define WAFFLE_GMU_BASE          0x03d68000u
#define WAFFLE_GMU_SIZE          0x00037000u
#define WAFFLE_GMU_REG(index)    (WAFFLE_GPU_BASE + 4u * (index) - WAFFLE_GMU_BASE)
#define WAFFLE_GMU_SYSRESET      WAFFLE_GMU_REG(0x1f800u)
#define WAFFLE_GMU_FW_INIT       WAFFLE_GMU_REG(0x1f81cu)
#define WAFFLE_GMU_COUNTER       WAFFLE_GMU_REG(0x1f880u)
#define WAFFLE_GMU_ITCM          WAFFLE_GMU_REG(0x1b400u)
#define WAFFLE_GMU_DTCM          WAFFLE_GMU_REG(0x1c400u)
#define WAFFLE_GPU_PDC_BASE     0x0b280000u
#define WAFFLE_GPU_PDC_SIZE     0x00010000u
#define WAFFLE_RSCC_BASE         0x03d50000u
#define WAFFLE_RSCC_SIZE         0x00010000u
#define WAFFLE_CX_MISC_BASE      0x03d9e000u
#define WAFFLE_CX_MISC_SIZE      0x00002000u
#define WAFFLE_GPU_SMMU_BASE     0x03da0000u
#define WAFFLE_GPU_SMMU_SIZE     0x00040000u
#define WAFFLE_GPU_QTB_BASE      0x03de8000u
#define WAFFLE_GPU_QTB_SIZE      0x00001000u
#define WAFFLE_GPU_GMU_FW        "gmu_gen70900.bin"
#define WAFFLE_GPU_SQE_FW        "gen70900_sqe.fw"
#define WAFFLE_GPU_AQE_FW        "gen70900_aqe.fw"
#define WAFFLE_GPU_ZAP_FW        "gen70900_zap.mbn"
/* Diagnostics93/94 only: successful native PLL1250/GMU625 start must precede it. */
bool waffle_gpu_native_runtime_clock(unsigned probe);
#endif
