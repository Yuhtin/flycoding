// Vendored from Stonkfly 78ef3e05ab0fa086032098558d893667068944a0, MIT.
// Upstream source SHA-256: e2d4d584f4633613277bb1bf6ea7ba20855c01a332ae2e9344ed7782604c8509
// See THIRD_PARTY.md and neural/PROVENANCE.md.  The kernel retains every CSR edge.
#include <cmath>
#include <cstdint>
extern "C" void memory_advance(
 int n,const int64_t* ptr,const int32_t* post,float* weight,float* v,float* g,int16_t* refractory,const float* drive,float* previous_drive,int32_t* queue,int32_t* queue_count,int64_t* clock,int steps,float dt,int32_t* counts,int32_t* active,uint8_t* flags,int32_t* nactive,int64_t* last,const uint8_t* kc_mask,const int8_t* dan_index,double* eligibility,int64_t* eligibility_last,int nplastic,const int64_t* plastic_edge,const int32_t* plastic_pre,const float* baseline_weight,const float* dan_gain,float eta,float tau_elig_ms,float floor_fraction,int learning_enabled,float* modulation,int64_t* modulation_last,const uint8_t* modulation_mask,const float* rest,float* adaptation,float adaptation_jump,float adaptation_tau) {
 const int delay=std::lround(1.8f/dt),rfc=std::lround(2.2f/dt),slots=delay+1;
 float av[1024],ag[1024],aa[1024];
 for(int i=0;i<1024;i++){av[i]=std::exp(-dt*i/20.f);ag[i]=std::exp(-dt*i/5.f);aa[i]=std::exp(-dt*i/adaptation_tau);}
 auto evolve=[&](int i,int64_t now,float current){int64_t d=now-last[i];if(d<=0)return;const int frozen=refractory[i]>0?refractory[i]-1:0;const int skip=(int)(d<frozen?d:frozen);if(skip>0&&adaptation[i]>0)adaptation[i]*=skip<1024?aa[skip]:std::exp(-dt*skip/adaptation_tau);refractory[i]=d>=refractory[i]?0:refractory[i]-d;d-=skip;if(d>0){const float a=d<1024?av[d]:std::exp(-dt*d/20.f),b=d<1024?ag[d]:std::exp(-dt*d/5.f);v[i]=rest[i]+(v[i]-rest[i])*a+current*(1.f-a)+g[i]*(a-b)/3.f;g[i]*=b;if(adaptation[i]>0){const float c=d<1024?aa[d]:std::exp(-dt*d/adaptation_tau);v[i]-=adaptation[i]*adaptation_tau/(adaptation_tau-20.f)*(c-a);adaptation[i]*=c;}}last[i]=now;};
 auto awaken=[&](int i){if(!flags[i]){flags[i]=1;active[(*nactive)++]=i;}};
 for(int i=0;i<n;i++)if(drive[i]!=previous_drive[i]){evolve(i,*clock-1,previous_drive[i]);previous_drive[i]=drive[i];awaken(i);}
 for(int t=0;t<steps;t++,(*clock)++){
  const int slot=*clock%slots,future=(*clock+delay)%slots;int kept=0,original=*nactive;
  for(int k=0;k<original;k++){const int i=active[k];evolve(i,*clock,drive[i]);if(refractory[i]==0&&v[i]>-45.f){queue[future*n+queue_count[future]++]=i;counts[i]++;if(kc_mask[i]){adaptation[i]+=adaptation_jump;eligibility[i]*=std::exp(-dt*(*clock-eligibility_last[i])/tau_elig_ms);eligibility[i]+=1.;eligibility_last[i]=*clock;}}const float gap=-45.f-rest[i];const bool can_fire=v[i]>-45.f||drive[i]>gap||drive[i]+g[i]>gap;if(can_fire)active[kept++]=i;else flags[i]=0;}
  *nactive=kept;
  for(int q=0;q<queue_count[slot];q++){const int i=queue[slot*n+q];if(modulation_mask[i]){for(int64_t e=ptr[i];e<ptr[i+1];e++){const int j=post[e];modulation[j]*=std::exp(-dt*(*clock-modulation_last[j])/100.f);modulation[j]+=std::abs(weight[e])/.275f;modulation_last[j]=*clock;}if(learning_enabled&&dan_index[i]>=0){for(int p=0;p<nplastic;p++){const int pre=plastic_pre[p];const double trace=eligibility[pre]*std::exp(-dt*(*clock-eligibility_last[pre])/tau_elig_ms);const float gain=dan_gain[dan_index[i]*nplastic+p];const int64_t edge=plastic_edge[p];const float candidate=weight[edge]*std::exp(-eta*gain*trace);const float lower=baseline_weight[p]*floor_fraction;weight[edge]=candidate>lower?candidate:lower;}}continue;}for(int64_t e=ptr[i];e<ptr[i+1];e++){const int j=post[e];evolve(j,*clock,drive[j]);if(refractory[j]==0){g[j]+=weight[e];awaken(j);}}}
  queue_count[slot]=0;for(int q=0;q<queue_count[future];q++){const int i=queue[future*n+q];v[i]=rest[i];g[i]=0.f;refractory[i]=rfc;}
 }
 for(int i=0;i<n;i++)evolve(i,*clock-1,drive[i]);
}
