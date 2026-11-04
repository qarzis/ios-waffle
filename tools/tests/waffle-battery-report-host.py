#!/usr/bin/env python3
"""Execute actual bounded sampler and BSD/native-power report boundary."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]

def function(source, signature):
    start = source.index(signature)
    at = source.index('{', start)
    end, depth = at + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'

adsp = (root/'kernel/files/bsd/dev/macan_adsp.c').read_text()
battery = (root/'kernel/files/bsd/dev/macan_battery.c').read_text()
header = (root/'kernel/files/bsd/sys/macan_input.h').read_text()
state = re.search(r'struct redwood_battery_state \{.*?\n\};', header, re.S)[0]
code = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
''' + state + r'''
static_assert(sizeof(redwood_battery_state)==60);
static bool battery_report_requested,stopping,link_failed;
static unsigned reads,fail_at,elapsed,stop_at,success;
static bool step_battery_readonly(){reads++;return !fail_at || reads!=fail_at;}
static void sleep_ms(unsigned ms){assert(ms==10);elapsed+=ms;if(stop_at && elapsed>=stop_at)stopping=true;}
static void test_log(const char *s,...){if(strstr(s,"passed=1"))success++;}
#define printf test_log
''' + function(adsp, 'static bool\nstep_battery_samples(') + r'''
#undef printf
static int battery_soc_percent,battery_voltage_mv,battery_current_ma,battery_temperature_c;
static int battery_present,battery_charger_present,battery_charging,battery_soc_estimated,battery_charger_action;
static int battery_full_uah,battery_design_uah,battery_cycles;
static uint64_t battery_updates;
static unsigned native_calls;
static redwood_battery_state native_state;
static void RedwoodBatteryReport(const void *p,unsigned size){
 assert(size==60);native_state=*static_cast<const redwood_battery_state*>(p);native_calls++;
}
''' + function(battery, 'void\nredwood_battery_report(') + r'''
static void reset(bool report){battery_report_requested=report;stopping=link_failed=false;reads=fail_at=elapsed=stop_at=success=0;}
int main(){
 reset(false);assert(step_battery_samples()&&reads==1&&elapsed==0&&success==0);
 reset(true);assert(step_battery_samples()&&reads==3&&elapsed==20000&&success==1);
 reset(true);fail_at=2;assert(!step_battery_samples()&&reads==2&&elapsed==10000&&!success);
 reset(true);stop_at=100;assert(!step_battery_samples()&&reads==1&&elapsed==100&&!success);
 reset(true);link_failed=true;assert(!step_battery_samples()&&reads==0&&!success);
 reset(true);stopping=true;assert(!step_battery_samples()&&reads==0&&!success);
 redwood_battery_state s{};s.size=sizeof(s);s.percent_hundredths=8300;s.voltage_uv=4182000;
 s.current_ua=32000;s.temperature_hundredths=3290;s.present=1;s.external=1;s.status=1;
 redwood_battery_report(&s);
 assert(battery_updates==1&&native_calls==1&&battery_soc_percent==83&&battery_voltage_mv==4182);
 assert(battery_temperature_c==33&&battery_current_ma==32&&battery_present&&battery_charger_present&&battery_charging);
 assert(native_state.percent_hundredths==8300&&native_state.temperature_hundredths==3290);
 s.percent_hundredths=8200;s.current_ua=-450000;s.external=0;s.status=2;
 redwood_battery_report(&s);assert(battery_updates==2&&native_calls==2&&battery_soc_percent==82);
 assert(battery_current_ma==-450&&!battery_charger_present&&!battery_charging&&native_state.current_ua==-450000);
 s.percent_hundredths=10000;redwood_battery_report(&s);assert(battery_updates==3&&battery_soc_percent==100);
}
'''
with tempfile.TemporaryDirectory() as directory:
    cpp = Path(directory)/'report.cpp'
    binary = Path(directory)/'report'
    cpp.write_text(code)
    subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                    str(cpp),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
print('PASS actual sampler bounded1/3 reads,20second intervals, failure/stop cancellation; actual BSD report83->82->100, native60byte ABI, units/status and update generations; IOKit callback mocked')
