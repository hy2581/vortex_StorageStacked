#pragma once
#include "axi_master.hh"
#include "axi_monitor.hh"
#include "systemc/tlm_port_wrapper.hh"
#include "params/StorageBridge.hh"
namespace storage_axi {
class AouBackend;
class Bridge : public sc_core::sc_module {
 public:
    SC_HAS_PROCESS(Bridge);
    explicit Bridge(const gem5::StorageBridgeParams&);
    gem5::Port& gem5_getPort(const std::string&, int idx = -1) override;
    void finish();
    ~Bridge();
 private:
    Bridge(sc_core::sc_module_name, const gem5::StorageBridgeParams&);
    Signals wires;
    sc_core::sc_clock clock;
    sc_core::sc_signal<bool> resetn{"resetn"};
    Master master;
    std::unique_ptr<AouBackend> aou;
    sc_gem5::TlmTargetWrapper<64> wrapper;
    AxiMonitor monitor;
    sc_core::sc_trace_file* vcd = nullptr;
    std::string directory;
    bool finished = false;
    void reset();
    void checkClock();
};
}
