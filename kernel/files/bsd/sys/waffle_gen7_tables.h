/* Generated from pinned OnePlus Gen7.9.1; DWORD register indices. */
#ifndef WAFFLE_GEN7_TABLES_H
#define WAFFLE_GEN7_TABLES_H
struct waffle_gen7_write { uint32_t index, mask, value, readback_mask; };
static const struct waffle_gen7_write waffle_gen7_disabled_setup[] = {
    {0x3c03u,0xffffffffu,0x00071620u,0xffffffffu}, /* GEN7_GBIF_QSB_SIDE0 */
    {0x3c04u,0xffffffffu,0x00071620u,0xffffffffu}, /* GEN7_GBIF_QSB_SIDE1 */
    {0x3c05u,0xffffffffu,0x00071620u,0xffffffffu}, /* GEN7_GBIF_QSB_SIDE2 */
    {0x3c06u,0xffffffffu,0x00071620u,0xffffffffu}, /* GEN7_GBIF_QSB_SIDE3 */
    {0x11u,0xffffffffu,0x02120212u,0xffffffffu}, /* GEN7_RBBM_GBIF_CLIENT_QOS_CNTL */
    {0xe3au,0xffffffffu,0x010240e0u,0xffffffffu}, /* GEN7_UCHE_GBIF_GX_CONFIG */
    {0x50bu,0xffffffffu,0xffffffffu,0x002f7fffu}, /* GEN7_RBBM_PERFCTR_GPU_BUSY_MASKED */
    {0xe09u,0xffffffffu,0xfffff000u,0xffffffffu}, /* GEN7_UCHE_TRAP_BASE_LO */
    {0xe0au,0xffffffffu,0x0001ffffu,0xffffffffu}, /* GEN7_UCHE_TRAP_BASE_HI */
    {0xe07u,0xffffffffu,0xfffff000u,0xffffffffu}, /* GEN7_UCHE_WRITE_THRU_BASE_LO */
    {0xe08u,0xffffffffu,0x0001ffffu,0xffffffffu}, /* GEN7_UCHE_WRITE_THRU_BASE_HI */
    {0xe0bu,0xffffffffu,0x01000000u,0xffffffffu}, /* GEN7_UCHE_GMEM_RANGE_MIN_LO */
    {0xe0cu,0xffffffffu,0x00000000u,0xffffffffu}, /* GEN7_UCHE_GMEM_RANGE_MIN_HI */
    {0xe0du,0xffffffffu,0x012fffffu,0xfffff000u}, /* GEN7_UCHE_GMEM_RANGE_MAX_LO */
    {0xe0eu,0xffffffffu,0x00000000u,0xffffffffu}, /* GEN7_UCHE_GMEM_RANGE_MAX_HI */
    {0xe17u,0xffffffffu,0x00800000u,0xffffffffu}, /* GEN7_UCHE_CACHE_WAYS */
    {0xe3cu,0xffffffffu,0x0006690eu,0xffffffffu}, /* GEN7_UCHE_CMDQ_CONFIG */
    {0x1f842u,0xffffffffu,0x00000004u,0xffffffffu}, /* GEN7_GMU_CX_GMU_POWER_COUNTER_SELECT_1 */
    {0x8e08u,0xffffffffu,0x00000816u,0xffffffffu}, /* GEN7_RB_NC_MODE_CNTL */
    {0xb604u,0xffffffffu,0x00000006u,0xffffffffu}, /* GEN7_TPL1_NC_MODE_CNTL */
    {0xb609u,0xffffffffu,0x3fe05ff4u,0xffffffffu}, /* GEN7_TPL1_BICUBIC_WEIGHTS_TABLE_1 */
    {0xb60au,0xffffffffu,0x3fa0ebeeu,0xffffffffu}, /* GEN7_TPL1_BICUBIC_WEIGHTS_TABLE_2 */
    {0xb60bu,0xffffffffu,0x3f5193edu,0xffffffffu}, /* GEN7_TPL1_BICUBIC_WEIGHTS_TABLE_3 */
    {0xb60cu,0xffffffffu,0x3f0243f0u,0xffffffffu}, /* GEN7_TPL1_BICUBIC_WEIGHTS_TABLE_4 */
    {0xae02u,0xffffffffu,0x00000026u,0xffffffffu}, /* GEN7_SP_NC_MODE_CNTL */
    {0x8602u,0xffffffffu,0x00000060u,0xffffffffu}, /* GEN7_GRAS_NC_MODE_CNTL */
    {0xe01u,0xffffffffu,0x00600000u,0xffffffffu}, /* GEN7_UCHE_MODE_CNTL */
    {0x1fu,0xffffffffu,0x40cfffffu,0xffffffffu}, /* GEN7_RBBM_INTERFACE_HANG_INT_CNTL */
    {0xe19u,0xffffffffu,0x00000081u,0xffffffffu}, /* GEN7_UCHE_CLIENT_PF */
    {0x8e28u,0x00080000u,0x00080000u,0x00080000u}, /* GEN7_RB_CMP_DBG_ECO_CNTL */
    {0xb602u,0xffffffffu,0x000c0700u,0xffffffffu}, /* GEN7_TPL1_DBG_ECO_CNTL1 */
    {0x23b0eu,0xffffffffu,0xff000000u,0xffffffffu}, /* GEN7_GPU_GMU_AO_GPU_CX_BUSY_MASK */
    {0x1f841u,0x000000ffu,0x00000020u,0x000000ffu}, /* GEN7_GMU_CX_GMU_POWER_COUNTER_SELECT_0 */
    {0x1f840u,0xffffffffu,0x00000001u,0xffffffffu}, /* GEN7_GMU_CX_GMU_POWER_COUNTER_ENABLE */
    {0x84fu,0xffffffffu,0x0000000bu,0xffffffffu}, /* GEN7_CP_PROTECT_CNTL */
    {0x850u,0xffffffffu,0x13fc0000u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 0 */
    {0x851u,0xffffffffu,0x0160050bu,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 1 */
    {0x852u,0xffffffffu,0x04f40584u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 2 */
    {0x853u,0xffffffffu,0x00000706u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 3 */
    {0x854u,0xffffffffu,0x007c0720u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 4 */
    {0x855u,0xffffffffu,0x027c0760u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 5 */
    {0x856u,0xffffffffu,0x82080800u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 6 */
    {0x857u,0xffffffffu,0x802008a0u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 7 */
    {0x858u,0xffffffffu,0x065408abu,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 8 */
    {0x859u,0xffffffffu,0x81340900u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 9 */
    {0x85au,0xffffffffu,0x82c8098du,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 10 */
    {0x85bu,0xffffffffu,0x86f80a41u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 11 */
    {0x85cu,0xffffffffu,0x80040df0u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 12 */
    {0x85du,0xffffffffu,0x80000e01u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 13 */
    {0x85eu,0xffffffffu,0x80200e07u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 14 */
    {0x85fu,0xffffffffu,0xd20c2840u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 15 */
    {0x860u,0xffffffffu,0x7ffc3cc4u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 16 */
    {0x861u,0xffffffffu,0x873c8630u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 17 */
    {0x862u,0xffffffffu,0x80008e00u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 18 */
    {0x863u,0xffffffffu,0x80008e08u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 19 */
    {0x864u,0xffffffffu,0x807c8e50u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 20 */
    {0x865u,0xffffffffu,0x8a1c8e79u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 21 */
    {0x866u,0xffffffffu,0x876c9624u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 22 */
    {0x867u,0xffffffffu,0x0bd09b0bu,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 23 */
    {0x868u,0xffffffffu,0x80049e1au,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 24 */
    {0x869u,0xffffffffu,0x80009e40u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 25 */
    {0x86au,0xffffffffu,0x80009e64u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 26 */
    {0x86bu,0xffffffffu,0x80049e70u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 27 */
    {0x86cu,0xffffffffu,0x861c9e78u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 28 */
    {0x86du,0xffffffffu,0x873ca630u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 29 */
    {0x86eu,0xffffffffu,0x8000ae02u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 30 */
    {0x86fu,0xffffffffu,0x803cae50u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 31 */
    {0x870u,0xffffffffu,0x800cae66u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 32 */
    {0x871u,0xffffffffu,0x800cae6fu,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 33 */
    {0x872u,0xffffffffu,0x8014b602u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 34 */
    {0x873u,0xffffffffu,0xbffcec00u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 35 */
    {0x874u,0xffffffffu,0x7ffcfc00u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 36 */
    {0x875u,0xffffffffu,0x05fd8400u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 37 */
    {0x876u,0xffffffffu,0xfffd8580u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 38 */
    {0x877u,0xffffffffu,0xfffda580u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 39 */
    {0x878u,0xffffffffu,0xfffdc580u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 40 */
    {0x879u,0xffffffffu,0x910df400u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 41 */
    {0x87au,0xffffffffu,0x01cdf844u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 42 */
    {0x87bu,0xffffffffu,0x808df87fu,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 43 */
    {0x87cu,0xffffffffu,0xfffdf8b8u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 44 */
    {0x87du,0xffffffffu,0x81fe7800u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 45 */
    {0x87eu,0xffffffffu,0x0e067880u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 46 */
    {0x87fu,0xffffffffu,0x80027c02u,0xffffffffu}, /* GEN7_CP_PROTECT_REG + 47 */
    {0x844u,0xffffffffu,0x0000006fu,0xffffffffu}, /* GEN7_CP_APRIV_CNTL */
    {0xad0u,0xffffffffu,0x0000000fu,0xffffffffu}, /* GEN7_CP_BV_APRIV_CNTL */
    {0xb31u,0xffffffffu,0x0000000fu,0xffffffffu}, /* GEN7_CP_LPAC_APRIV_CNTL */
    {0xb78u,0xffffffffu,0x00000001u,0xffffffffu}, /* GEN7_CP_AQE_APRIV_CNTL */
    {0x3c00u,0xe0000000u,0x20000000u,0xe0000000u}, /* GEN7_GBIF_CX_CONFIG */
    {0xf803u,0xffffffffu,0x00000000u,0xffffffffu}, /* GEN7_RBBM_SECVID_TSB_CNTL */
    {0xf800u,0xffffffffu,0xa0000000u,0xffffffffu}, /* GEN7_RBBM_SECVID_TSB_TRUSTED_BASE_LO */
    {0xf801u,0xffffffffu,0x00000000u,0xffffffffu}, /* GEN7_RBBM_SECVID_TSB_TRUSTED_BASE_HI */
    {0xf802u,0xffffffffu,0x00400000u,0xffffffffu}, /* GEN7_RBBM_SECVID_TSB_TRUSTED_SIZE */
};
static const struct waffle_gen7_write waffle_gen7_ao_hwcg[] = {
    {0x23b09u,0xffffffffu,0x00020202u,0xffffffffu},
    {0x23b0au,0xffffffffu,0x00010111u,0xffffffffu},
    {0x23b0bu,0xffffffffu,0x00005555u,0xffffffffu},
};
#define WAFFLE_GEN7_RBBM_CLOCK_CNTL_GLOBAL 0xadu
#define WAFFLE_GEN7_RBBM_CGC_GLOBAL_LOAD_CMD 0x11eu
#define WAFFLE_GEN7_RBBM_CGC_P2S_TRIG_CMD 0x11fu
#define WAFFLE_GEN7_RBBM_CGC_P2S_STATUS 0x122u
static const uint32_t waffle_gen7_ifpc_restore[] = {
    0xb604u, /* GEN7_TPL1_NC_MODE_CNTL */
    0xae02u, /* GEN7_SP_NC_MODE_CNTL */
    0x843u, /* GEN7_CP_DBG_ECO_CNTL */
    0x84fu, /* GEN7_CP_PROTECT_CNTL */
    0xb09u, /* GEN7_CP_LPAC_PROTECT_CNTL */
    0x850u, /* GEN7_CP_PROTECT_REG */
    0x851u, /* GEN7_CP_PROTECT_REG+1 */
    0x852u, /* GEN7_CP_PROTECT_REG+2 */
    0x853u, /* GEN7_CP_PROTECT_REG+3 */
    0x854u, /* GEN7_CP_PROTECT_REG+4 */
    0x855u, /* GEN7_CP_PROTECT_REG+5 */
    0x856u, /* GEN7_CP_PROTECT_REG+6 */
    0x857u, /* GEN7_CP_PROTECT_REG+7 */
    0x858u, /* GEN7_CP_PROTECT_REG+8 */
    0x859u, /* GEN7_CP_PROTECT_REG+9 */
    0x85au, /* GEN7_CP_PROTECT_REG+10 */
    0x85bu, /* GEN7_CP_PROTECT_REG+11 */
    0x85cu, /* GEN7_CP_PROTECT_REG+12 */
    0x85du, /* GEN7_CP_PROTECT_REG+13 */
    0x85eu, /* GEN7_CP_PROTECT_REG+14 */
    0x85fu, /* GEN7_CP_PROTECT_REG+15 */
    0x860u, /* GEN7_CP_PROTECT_REG+16 */
    0x861u, /* GEN7_CP_PROTECT_REG+17 */
    0x862u, /* GEN7_CP_PROTECT_REG+18 */
    0x863u, /* GEN7_CP_PROTECT_REG+19 */
    0x864u, /* GEN7_CP_PROTECT_REG+20 */
    0x865u, /* GEN7_CP_PROTECT_REG+21 */
    0x866u, /* GEN7_CP_PROTECT_REG+22 */
    0x867u, /* GEN7_CP_PROTECT_REG+23 */
    0x868u, /* GEN7_CP_PROTECT_REG+24 */
    0x869u, /* GEN7_CP_PROTECT_REG+25 */
    0x86au, /* GEN7_CP_PROTECT_REG+26 */
    0x86bu, /* GEN7_CP_PROTECT_REG+27 */
    0x86cu, /* GEN7_CP_PROTECT_REG+28 */
    0x86du, /* GEN7_CP_PROTECT_REG+29 */
    0x86eu, /* GEN7_CP_PROTECT_REG+30 */
    0x86fu, /* GEN7_CP_PROTECT_REG+31 */
    0x870u, /* GEN7_CP_PROTECT_REG+32 */
    0x871u, /* GEN7_CP_PROTECT_REG+33 */
    0x872u, /* GEN7_CP_PROTECT_REG+34 */
    0x873u, /* GEN7_CP_PROTECT_REG+35 */
    0x874u, /* GEN7_CP_PROTECT_REG+36 */
    0x875u, /* GEN7_CP_PROTECT_REG+37 */
    0x876u, /* GEN7_CP_PROTECT_REG+38 */
    0x877u, /* GEN7_CP_PROTECT_REG+39 */
    0x878u, /* GEN7_CP_PROTECT_REG+40 */
    0x879u, /* GEN7_CP_PROTECT_REG+41 */
    0x87au, /* GEN7_CP_PROTECT_REG+42 */
    0x87bu, /* GEN7_CP_PROTECT_REG+43 */
    0x87cu, /* GEN7_CP_PROTECT_REG+44 */
    0x87du, /* GEN7_CP_PROTECT_REG+45 */
    0x87eu, /* GEN7_CP_PROTECT_REG+46 */
    0x87fu, /* GEN7_CP_PROTECT_REG+47 */
    0x98du, /* GEN7_CP_AHB_CNTL */
    0xb609u, /* GEN7_TPL1_BICUBIC_WEIGHTS_TABLE_1 */
    0xb60au, /* GEN7_TPL1_BICUBIC_WEIGHTS_TABLE_2 */
    0xb60bu, /* GEN7_TPL1_BICUBIC_WEIGHTS_TABLE_3 */
    0xb60cu, /* GEN7_TPL1_BICUBIC_WEIGHTS_TABLE_4 */
};
static const uint32_t waffle_gen7_preemption_restore[] = {
    0xe09u, /* GEN7_UCHE_TRAP_BASE_LO */
    0xe0au, /* GEN7_UCHE_TRAP_BASE_HI */
    0xe07u, /* GEN7_UCHE_WRITE_THRU_BASE_LO */
    0xe08u, /* GEN7_UCHE_WRITE_THRU_BASE_HI */
    0xe0bu, /* GEN7_UCHE_GMEM_RANGE_MIN_LO */
    0xe0cu, /* GEN7_UCHE_GMEM_RANGE_MIN_HI */
    0xe0du, /* GEN7_UCHE_GMEM_RANGE_MAX_LO */
    0xe0eu, /* GEN7_UCHE_GMEM_RANGE_MAX_HI */
    0xe17u, /* GEN7_UCHE_CACHE_WAYS */
    0xe01u, /* GEN7_UCHE_MODE_CNTL */
    0x8e08u, /* GEN7_RB_NC_MODE_CNTL */
    0x8e28u, /* GEN7_RB_CMP_DBG_ECO_CNTL */
    0x8602u, /* GEN7_GRAS_NC_MODE_CNTL */
    0x8e50u, /* GEN7_RB_CONTEXT_SWITCH_GMEM_SAVE_RESTORE */
    0xe3au, /* GEN7_UCHE_GBIF_GX_CONFIG */
    0xe19u, /* GEN7_UCHE_CLIENT_PF */
    0xb602u, /* GEN7_TPL1_DBG_ECO_CNTL1 */
};
#endif
