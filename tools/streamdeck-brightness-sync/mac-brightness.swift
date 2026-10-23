import Foundation
import CoreGraphics

typealias DSGetBrightness = @convention(c) (CGDirectDisplayID, UnsafeMutablePointer<Float>) -> Int32

guard let handle = dlopen(
  "/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices",
  RTLD_LAZY
) else {
  fputs("error: DisplayServices unavailable\n", stderr)
  exit(2)
}
defer { dlclose(handle) }

guard let sym = dlsym(handle, "DisplayServicesGetBrightness") else {
  fputs("error: DisplayServicesGetBrightness missing\n", stderr)
  exit(2)
}

let getBrightness = unsafeBitCast(sym, to: DSGetBrightness.self)
var value: Float = 0
let rc = getBrightness(CGMainDisplayID(), &value)
guard rc == 0 else {
  fputs("error: get brightness failed rc=\(rc)\n", stderr)
  exit(3)
}

let pct = Int((max(0, min(1, value)) * 100).rounded())
print(pct)
