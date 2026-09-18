#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <IOKit/IOCFPlugIn.h>
#include <IOKit/usb/IOUSBLib.h>
#include <IOKit/usb/USB.h>

#define HUB_LOC 1249280
#define DECK_LOC 1249536
#define DECK_PORT 1
#define PORT_POWER 8
#define PORT_RESET 4

static io_service_t find_by_class_loc(const char *cls, int location) {
    CFMutableDictionaryRef matching = IOServiceMatching(cls);
    if (!matching) {
        return 0;
    }
    io_iterator_t iter = 0;
    if (IOServiceGetMatchingServices(kIOMainPortDefault, matching, &iter) != KERN_SUCCESS) {
        return 0;
    }
    io_service_t service, found = 0;
    while ((service = IOIteratorNext(iter))) {
        CFNumberRef locRef = IORegistryEntryCreateCFProperty(service, CFSTR("locationID"), kCFAllocatorDefault, 0);
        int loc = -1;
        if (locRef) {
            CFNumberGetValue(locRef, kCFNumberSInt32Type, &loc);
            CFRelease(locRef);
        }
        if (loc == location) {
            found = service;
            break;
        }
        IOObjectRelease(service);
    }
    IOObjectRelease(iter);
    return found;
}

static int hub_control(int port, UInt8 request, UInt16 feature) {
    io_service_t iface = 0;
    CFMutableDictionaryRef matching = IOServiceMatching("IOUSBHostInterface");
    io_iterator_t iter = 0;
    if (IOServiceGetMatchingServices(kIOMainPortDefault, matching, &iter) != KERN_SUCCESS) {
        fprintf(stderr, "no IOUSBHostInterface iterator\n");
        return 1;
    }
    io_service_t service;
    while ((service = IOIteratorNext(iter))) {
        CFNumberRef locRef = IORegistryEntryCreateCFProperty(service, CFSTR("locationID"), kCFAllocatorDefault, 0);
        CFNumberRef clsRef = IORegistryEntryCreateCFProperty(service, CFSTR("bInterfaceClass"), kCFAllocatorDefault, 0);
        int loc = -1, cls = -1;
        if (locRef) {
            CFNumberGetValue(locRef, kCFNumberSInt32Type, &loc);
            CFRelease(locRef);
        }
        if (clsRef) {
            CFNumberGetValue(clsRef, kCFNumberSInt32Type, &cls);
            CFRelease(clsRef);
        }
        if (loc == HUB_LOC && cls == 9) {
            iface = service;
            break;
        }
        IOObjectRelease(service);
    }
    IOObjectRelease(iter);
    if (!iface) {
        fprintf(stderr, "hub class-9 interface at %d not found\n", HUB_LOC);
        return 1;
    }

    IOCFPlugInInterface **plugin = NULL;
    SInt32 score = 0;
    kern_return_t kr = IOCreatePlugInInterfaceForService(
        iface, kIOUSBInterfaceUserClientTypeID, kIOCFPlugInInterfaceID, &plugin, &score
    );
    if (kr != KERN_SUCCESS || !plugin) {
        fprintf(stderr, "hub interface plugin failed 0x%x\n", kr);
        IOObjectRelease(iface);
        return 1;
    }
    IOUSBInterfaceInterface800 **intf = NULL;
    HRESULT hr = (*plugin)->QueryInterface(plugin, CFUUIDGetUUIDBytes(kIOUSBInterfaceInterfaceID800), (LPVOID *)&intf);
    IODestroyPlugInInterface(plugin);
    if (hr != S_OK || !intf) {
        fprintf(stderr, "hub QueryInterface failed 0x%x\n", (unsigned)hr);
        IOObjectRelease(iface);
        return 1;
    }
    IOReturn open = (*intf)->USBInterfaceOpen(intf);
    if (open != kIOReturnSuccess) {
        fprintf(stderr, "USBInterfaceOpen hub 0x%x, trying seize\n", open);
        open = (*intf)->USBInterfaceOpenSeize(intf);
    }
    if (open != kIOReturnSuccess) {
        fprintf(stderr, "USBInterfaceOpenSeize hub failed 0x%x\n", open);
        (*intf)->Release(intf);
        IOObjectRelease(iface);
        return 1;
    }

    IOUSBDevRequest req;
    req.bmRequestType = USBmakebmRequestType(kUSBOut, kUSBClass, kUSBOther);
    req.bRequest = request;
    req.wValue = feature;
    req.wIndex = (UInt16)port;
    req.wLength = 0;
    req.pData = NULL;
    req.wLenDone = 0;
    IOReturn cr = (*intf)->ControlRequest(intf, 0, &req);
    fprintf(stderr, "hub ControlRequest req=%u feature=%u port=%d -> 0x%x\n", request, feature, port, cr);
    (*intf)->USBInterfaceClose(intf);
    (*intf)->Release(intf);
    IOObjectRelease(iface);
    return cr == kIOReturnSuccess ? 0 : 1;
}

static int deck_reenumerate(UInt32 options) {
    io_service_t service = find_by_class_loc("IOUSBHostDevice", DECK_LOC);
    if (!service) {
        fprintf(stderr, "stream deck USB node not found at %d\n", DECK_LOC);
        return 1;
    }
    IOCFPlugInInterface **plugin = NULL;
    SInt32 score = 0;
    kern_return_t kr = IOCreatePlugInInterfaceForService(
        service, kIOUSBDeviceUserClientTypeID, kIOCFPlugInInterfaceID, &plugin, &score
    );
    if (kr != KERN_SUCCESS || !plugin) {
        fprintf(stderr, "deck plugin failed 0x%x\n", kr);
        IOObjectRelease(service);
        return 1;
    }
    IOUSBDeviceInterface **dev = NULL;
    HRESULT hr = (*plugin)->QueryInterface(plugin, CFUUIDGetUUIDBytes(kIOUSBDeviceInterfaceID650), (LPVOID *)&dev);
    IODestroyPlugInInterface(plugin);
    if (hr != S_OK || !dev) {
        fprintf(stderr, "deck QueryInterface failed\n");
        IOObjectRelease(service);
        return 1;
    }
    IOReturn re = (*dev)->USBDeviceReEnumerate(dev, options);
    fprintf(stderr, "USBDeviceReEnumerate options=0x%x -> 0x%x\n", options, re);
    if (re != kIOReturnSuccess) {
        IOReturn open = (*dev)->USBDeviceOpenSeize(dev);
        fprintf(stderr, "USBDeviceOpenSeize -> 0x%x\n", open);
        if (open == kIOReturnSuccess) {
            IOReturn rst = (*dev)->ResetDevice(dev);
            fprintf(stderr, "ResetDevice -> 0x%x\n", rst);
            re = rst;
            (*dev)->USBDeviceClose(dev);
        }
    }
    (*dev)->Release(dev);
    IOObjectRelease(service);
    return re == kIOReturnSuccess ? 0 : 1;
}

static int probe_port(void) {
    io_service_t port = find_by_class_loc("AppleUSB20HubPort", DECK_LOC);
    if (!port) {
        fprintf(stderr, "AppleUSB20HubPort not found\n");
        return 1;
    }
    kern_return_t kr = IOServiceRequestProbe(port, 0);
    fprintf(stderr, "IOServiceRequestProbe AppleUSB20HubPort -> 0x%x\n", kr);
    IOObjectRelease(port);
    return kr == KERN_SUCCESS ? 0 : 1;
}

int main(void) {
    fprintf(stderr, "=== hub port 1 POWER off ===\n");
    hub_control(DECK_PORT, kUSBRqClearFeature, PORT_POWER);
    sleep(2);
    fprintf(stderr, "=== hub port 1 POWER on ===\n");
    hub_control(DECK_PORT, kUSBRqSetFeature, PORT_POWER);
    sleep(1);
    fprintf(stderr, "=== hub port 1 RESET ===\n");
    hub_control(DECK_PORT, kUSBRqSetFeature, PORT_RESET);
    sleep(1);
    fprintf(stderr, "=== capture/release reenumerate ===\n");
    deck_reenumerate(kUSBReEnumerateCaptureDeviceMask);
    usleep(500000);
    deck_reenumerate(kUSBReEnumerateReleaseDeviceMask);
    probe_port();
    return 0;
}
