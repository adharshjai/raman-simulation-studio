// The plain data types of Hamamatsu's wrrusb2a.dll (namespace WRRUSB2_DLL, class Usb2Struct) that the
// capture backend and its simulator use: the module and spectrometer information classes and the
// return codes. The vendor library itself is proprietary and not part of this repository, so this
// build has the simulator only (SimulatedDevice.cs). Names, field names and numeric values follow the
// library's public API, so the code that uses them is the same as in a build with the real library.
namespace WRRUSB2_DLL
{
    public class Usb2Struct
    {
        /// <summary>Sensor type code of the C13560's 2048-pixel CMOS sensor.</summary>
        public static string D_TYPE_CMOS_2048PIXEL = "F4";

        public class CModuleInformation
        {
            public string vender;
            public string product;
            public string serial;
            public string firmware;
            public string driver;
            public string library;
        }

        public class CSpectroInformation
        {
            public string unit;
            public string sensor;
        }

        /// <summary>Return codes of every USB2_* call (0 is success).</summary>
        public enum Cusb2Err
        {
            usb2Success = 0,
            usb2Err_unsuccess = 1,
            usb2Err_notList = 2,
            usb2Err_notAccess = 3,
            usb2Err_notFrame = 4,
            usb2Err_notAcPower = 5,
            usb2Err_notImage = 6,
            usb2Err_notBuffer = 7,
            usb2Err_notData = 8,
            usb2Err_notDownload = 9,
            usb2Err_invalidDeviceIndex = 10,
            usb2Err_invalidMode = 11,
            usb2Err_invalidParameter = 12,
            usb2Err_invalidTriggermode = 13,
            usb2Err_invalidTriggerpolarity = 14,
            usb2Err_invalidTriggeroutput = 15,
            usb2Err_invalidBinning = 16,
            usb2Err_invalidPosition = 17,
            usb2Err_invalidSize = 18,
            usb2Err_invalidGain = 19,
            usb2Err_invalidOffset = 20,
            usb2Err_invalidCoolingstatus = 21,
            usb2Err_invalidFrame = 22,
            usb2Err_invalidEventID = 23,
            usb2Err_invalidEventhandle = 24,
            usb2Err_invalidData = 25,
            usb2Err_invalidIndex = 26,
            usb2Err_invalidNumber = 27,
            usb2Err_invalidAddress = 28,
            usb2Err_invalidLength = 29,
            usb2Err_overTime = 30,
            usb2Err_underTime = 31,
            usb2Err_overTemperature = 32,
            usb2Err_underTemperature = 33,
            usb2Err_overArea = 34,
            usb2Err_nowCapturing = 35,
            usb2Err_nowFirmUpdate = 36,
            usb2Err_initialized = 37,
            usb2Err_opened = 38,
            usb2Err_existDevice = 39,
            usb2Err_FirmCorrupted = 40,
            usb2Err_ReadImageStatus = 41,
            usb2Err_InvalidEepromParameter = 42,
        }
    }
}
