#include <stdio.h>
#include <stdlib.h>
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <IOKit/IOCFPlugIn.h>
#include <IOKit/usb/IOUSBLib.h>

static int reset_service(io_service_t service) {
    IOCFPlugInInterface **plugin = NULL;
    SInt32 score = 0;
    kern_return_t kr = IOCreatePlugInInterfaceForService(
        service,
        kIOUSBDeviceUserClientTypeID,
        kIOCFPlugInInterfaceID,
        &plugin,
        &score
    );
    if (kr != KERN_SUCCESS || plugin == NULL) {
        fprintf(stderr, "IOCreatePlugInInterfaceForService failed 0x%x\n", kr);
        return 1;
    }

    IOUSBDeviceInterface **dev = NULL;
    HRESULT hr = (*plugin)->QueryInterface(
        plugin,
        CFUUIDGetUUIDBytes(kIOUSBDeviceInterfaceID650),
        (LPVOID *)&dev
    );
    IODestroyPlugInInterface(plugin);
    if (hr != S_OK || dev == NULL) {
        fprintf(stderr, "QueryInterface failed 0x%x\n", (unsigned)hr);
        return 1;
    }

    IOReturn open = (*dev)->USBDeviceOpenSeize(dev);
    if (open != kIOReturnSuccess) {
        fprintf(stderr, "USBDeviceOpenSeize 0x%x, falling back to USBDeviceOpen\n", open);
        open = (*dev)->USBDeviceOpen(dev);
    }
    if (open != kIOReturnSuccess) {
        fprintf(stderr, "USBDeviceOpen failed 0x%x, probing instead\n", open);
        (*dev)->Release(dev);
        kern_return_t probe = IOServiceRequestProbe(service, 0);
        fprintf(stderr, "IOServiceRequestProbe -> 0x%x\n", probe);
        return probe == KERN_SUCCESS ? 0 : 1;
    }

    IOReturn re = (*dev)->USBDeviceReEnumerate(dev, 0);
    fprintf(stderr, "USBDeviceReEnumerate -> 0x%x\n", re);
    if (re != kIOReturnSuccess) {
        IOReturn rst = (*dev)->ResetDevice(dev);
        fprintf(stderr, "ResetDevice -> 0x%x\n", rst);
        re = rst;
    }

    (*dev)->USBDeviceClose(dev);
    (*dev)->Release(dev);
    return re == kIOReturnSuccess ? 0 : 1;
}

int main(int argc, char **argv) {
    int vid = 0x0fd9;
    int pid = 0x0084;
    int location = -1;
    if (argc >= 3) {
        vid = (int)strtol(argv[1], NULL, 0);
        pid = (int)strtol(argv[2], NULL, 0);
    }
    if (argc >= 4) {
        location = (int)strtol(argv[3], NULL, 0);
    }

    CFMutableDictionaryRef matching = IOServiceMatching("IOUSBHostDevice");
    if (matching == NULL) {
        fprintf(stderr, "IOServiceMatching failed\n");
        return 1;
    }
    CFNumberRef nvid = CFNumberCreate(kCFAllocatorDefault, kCFNumberSInt32Type, &vid);
    CFNumberRef npid = CFNumberCreate(kCFAllocatorDefault, kCFNumberSInt32Type, &pid);
    CFDictionarySetValue(matching, CFSTR("idVendor"), nvid);
    CFDictionarySetValue(matching, CFSTR("idProduct"), npid);
    CFRelease(nvid);
    CFRelease(npid);

    io_iterator_t iter = 0;
    kern_return_t kr = IOServiceGetMatchingServices(kIOMainPortDefault, matching, &iter);
    if (kr != KERN_SUCCESS) {
        fprintf(stderr, "IOServiceGetMatchingServices failed 0x%x\n", kr);
        return 1;
    }

    int rc = 2;
    io_service_t service;
    while ((service = IOIteratorNext(iter))) {
        if (location >= 0) {
            CFNumberRef locRef = IORegistryEntryCreateCFProperty(service, CFSTR("locationID"), kCFAllocatorDefault, 0);
            int foundLoc = -1;
            if (locRef) {
                CFNumberGetValue(locRef, kCFNumberSInt32Type, &foundLoc);
                CFRelease(locRef);
            }
            if (foundLoc != location) {
                IOObjectRelease(service);
                continue;
            }
        }
        rc = reset_service(service);
        IOObjectRelease(service);
        if (rc == 0) {
            break;
        }
    }
    IOObjectRelease(iter);

    if (rc == 2) {
        fprintf(stderr, "no USB device vid=0x%04x pid=0x%04x\n", vid, pid);
    }
    return rc;
}
