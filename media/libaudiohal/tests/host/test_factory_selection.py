#!/usr/bin/env python3
"""Run extracted FactoryHal selection with ASan/UBSan (host g++ required).

Usage: python3 media/libaudiohal/tests/host/test_factory_selection.py [git_revision]
The optional revision supports the pre-restoration negative control. This executes
production version tables and createPreferredImpl(), but models the generated
version record, service discovery and library construction. It does not exercise
Binder, dlopen, actual exported factories, the HAL, or device audio.
"""
import pathlib,subprocess,tempfile,sys
hal=pathlib.Path(__file__).resolve().parents[2]
wt=hal.parents[1]
source=(hal/'FactoryHal.cpp').read_text()
if len(sys.argv)>1:
 source=subprocess.check_output(['git','-C',str(wt),'show',sys.argv[1]+':media/libaudiohal/FactoryHal.cpp'],text=True)
versions=source[source.index('static const std::array'):source.index('bool createHalService')]
selection=source[source.index('void *createPreferredImpl'):source.rindex('}  // namespace android::detail')]
harness=r'''
#include <algorithm>
#include <array>
#include <map>
#include <memory>
#include <string>
#include <tuple>
#include <utility>
#include <vector>
#include <cassert>
#include <iostream>
#define ALOGE(...) ((void)0)
// Model generated version record and service-manager/dlopen boundary only.
struct AudioHalVersionInfo {
 enum class Type { AIDL, HIDL };
 Type type; int major,minor;
 AudioHalVersionInfo(Type t,int a,int b):type(t),major(a),minor(b){}
 Type getType()const{return type;} int getMajorVersion()const{return major;}
 std::string toString()const{return std::to_string(major)+"."+std::to_string(minor);}
 bool operator<(const AudioHalVersionInfo& v)const{return std::tie(type,major,minor)<std::tie(v.type,v.major,v.minor);}
};
using InterfaceName=std::pair<std::string,std::string>;
using T=AudioHalVersionInfo::Type;
struct Service { bool core; T type; int major,minor; };
std::vector<Service> services;
int creates=0; bool requestedCore=false,creationSucceeds=true; T chosenType=T::HIDL; int chosenMajor=0,chosenMinor=0;
bool hasHalService(const InterfaceName&i,const AudioHalVersionInfo&v){
 bool core=i.second=="IDevicesFactory"||i.second=="IModule";
 return std::any_of(services.begin(),services.end(),[&](auto&s){return s.core==core&&s.type==v.type&&s.major==v.major&&s.minor==v.minor;});
}
bool createHalService(const AudioHalVersionInfo&v,bool core,void**p){
 ++creates;requestedCore=core;chosenType=v.type;chosenMajor=v.major;chosenMinor=v.minor;
 *p=&creates;return creationSucceeds;
}
'''+versions+selection+r'''
void setup(std::initializer_list<Service>s){services=s;creates=0;creationSucceeds=true;}
int main(){
 setup({{true,T::HIDL,5,0},{false,T::HIDL,5,0}});
 assert(createPreferredImpl(true)&&creates==1&&requestedCore&&chosenMajor==5);
 assert(createPreferredImpl(false)&&creates==2&&!requestedCore&&chosenMajor==5);
 setup({{true,T::HIDL,5,0}});assert(!createPreferredImpl(true)&&creates==0);
 setup({{false,T::HIDL,5,0}});assert(!createPreferredImpl(false)&&creates==0);
 setup({{true,T::HIDL,5,0},{false,T::HIDL,6,0}});assert(!createPreferredImpl(true)&&creates==0);
 setup({{true,T::AIDL,1,0},{false,T::HIDL,5,0}});assert(!createPreferredImpl(false)&&creates==0);
 setup({{true,T::HIDL,5,0},{false,T::HIDL,5,0},{true,T::HIDL,6,0},{false,T::HIDL,6,0}});
 assert(createPreferredImpl(true)&&chosenMajor==6);
 setup({{true,T::HIDL,7,0},{false,T::HIDL,7,1}});assert(createPreferredImpl(false)&&chosenMajor==7&&chosenMinor==1);
 setup({{true,T::AIDL,1,0},{false,T::AIDL,1,0},{true,T::HIDL,5,0},{false,T::HIDL,5,0}});
 assert(createPreferredImpl(true)&&chosenType==T::AIDL);
 setup({{true,T::HIDL,5,0},{false,T::HIDL,5,0}});creationSucceeds=false;
 assert(!createPreferredImpl(true)&&creates==1);
 setup({});assert(!createPreferredImpl(true)&&creates==0);
 std::cout<<"11 factory selection assertions passed; discovery/construction/version record modeled\n";
}
'''
with tempfile.TemporaryDirectory(prefix='audio5-factory-') as d:
 p=pathlib.Path(d);(p/'test.cpp').write_text(harness)
 subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
