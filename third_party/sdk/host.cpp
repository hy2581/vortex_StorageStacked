#include <vortex2.h>
#include "project_config.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <string>

#define CHECK(call) do { const vx_result_t r=(call); if(r!=VX_SUCCESS) { \
    std::fprintf(stderr,"Runtime error: %s: %s\n",#call,vx_result_string(r)); return 1; } } while(0)

int main(int argc,char** argv) {
    if(argc!=2) {std::fprintf(stderr,"usage: host.elf program.vxbin\n");return 2;}
    vx_device_h device=nullptr;CHECK(vx_device_open(0,&device));
    vx_queue_info_t info{sizeof(info),nullptr,VX_QUEUE_PRIORITY_NORMAL,0};
    vx_queue_h queue=nullptr;CHECK(vx_queue_create(device,&info,&queue));
    vx_buffer_h buffer=nullptr;
    CHECK(vx_buffer_reserve(device,0x90000000ull,0x60000,VX_MEM_READ_WRITE|VX_MEM_PHYS,&buffer));
    vx_module_h module=nullptr;vx_kernel_h kernel=nullptr;
    CHECK(vx_module_load_file(device,argv[1],&module));
    CHECK(vx_module_get_kernel(module,"main",&kernel));
    vx_launch_info_t launch{};launch.struct_size=sizeof(launch);launch.kernel=kernel;
    launch.ndim=1;launch.grid_dim[0]=APP_WORKGROUPS;launch.block_dim[0]=1;
    vx_event_h event=nullptr;CHECK(vx_enqueue_launch(queue,&launch,0,nullptr,&event));
    CHECK(vx_event_wait_value(event,1,VX_TIMEOUT_INFINITE));
    unsigned status=0;
    for(const auto& range:readback_ranges) {
        std::vector<uint8_t> bytes(range.bytes);
        vx_event_h read=nullptr;
        CHECK(vx_enqueue_read(queue,bytes.data(),buffer,range.offset,range.bytes,0,nullptr,&read));
        CHECK(vx_event_wait_value(read,1,VX_TIMEOUT_INFINITE));
        static constexpr char hex[]="0123456789abcdef";
        std::string line;line.reserve(bytes.size()*2);
        for(auto byte:bytes) {line+=hex[byte>>4];line+=hex[byte&15];}
        std::printf("READBACK %08x %s\n",unsigned(0x90000000u+range.offset),line.c_str());
        if(range.offset<=0x5000c && range.offset+range.bytes>=0x50010) {
            unsigned i=0x5000c-range.offset;
            status=unsigned(bytes[i])|(unsigned(bytes[i+1])<<8)|(unsigned(bytes[i+2])<<16)|(unsigned(bytes[i+3])<<24);
        }
        vx_event_release(read);
    }
    vx_event_release(event);vx_kernel_release(kernel);vx_module_release(module);
    vx_buffer_release(buffer);vx_queue_release(queue);
    vx_device_dump_perf(device,stdout);vx_device_release(device);
    std::printf("DEVICE_STATUS %08x\n",status);
    return status==0x600d0000u?0:1;
}
