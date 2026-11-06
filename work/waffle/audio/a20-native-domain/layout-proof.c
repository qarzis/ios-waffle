#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
/* Exact config-independent prefixes from pinned OnePlus arm-smmu.h. */
struct cfg {uint8_t cb,irq;uint16_t asid;uint32_t procid,sctlr;int cbar,fmt;bool flush;};
struct domain_prefix {void *smmu,*dev,*ops;unsigned long quirks;bool coherent;void *flush;struct cfg cfg;int stage;};
struct smmu_prefix {void *dev,*base;uint64_t ioaddr;unsigned numpage,pgshift,features,options;int version,model;void *impl;unsigned banks,s2banks;unsigned long bitmap[2];void *cbs;};
struct cb {uint64_t ttbr[2];uint32_t tcr[2],mair[2],sctlr;struct cfg *cfg;};
_Static_assert(sizeof(void*)==8,"64-bit native ABI");
_Static_assert(offsetof(struct domain_prefix,cfg)==48,"cfg offset");
_Static_assert(offsetof(struct domain_prefix,stage)==72,"stage offset");
_Static_assert(offsetof(struct smmu_prefix,ioaddr)==16,"ioaddr offset");
_Static_assert(offsetof(struct smmu_prefix,numpage)==24,"numpage offset");
_Static_assert(offsetof(struct smmu_prefix,cbs)==80,"cached banks pointer");
_Static_assert(sizeof(struct cb)==48,"cached bank stride");
_Static_assert(46*sizeof(struct cb)==2208,"CB46 base");
_Static_assert(offsetof(struct cb,sctlr)==32,"cached SCTLR offset");
int main(void){return 0;}
