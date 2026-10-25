'use strict';

// A cursor belongs to one mounted feed. Failed requests never advance it.
export function createProductFeed({initial, size, fetchPage}){
  let page=1, loading=false, disposed=false, hasMore=initial.length===size;
  const seen=new Set(initial.map(product=>product.id));
  return {
    get hasMore(){ return !disposed && hasMore; },
    get loading(){ return loading; },
    dispose(){ disposed=true; },
    async next(){
      if (disposed || loading || !hasMore) return [];
      loading=true;
      try{
        const products=await fetchPage(page+1);
        if (disposed) return [];
        page++; hasMore=products.length===size;
        return products.filter(product=>{
          if (seen.has(product.id)) return false;
          seen.add(product.id); return true;
        });
      }finally{ loading=false; }
    }
  };
}
