// The subset of WRRUSB2_DLL.WRRUSB2 that SampleApl.cpp calls, with the DLL's exact signatures
// (class WRRUSB2_DLL.WRRUSB2 of Hamamatsu's wrrusb2a.dll). SampleApl.cpp uses 29 distinct
// USB2_* operations; a grep for "USB2_" also hits the namespace token WRRUSB2_DLL, which is not one.
using WRRUSB2_DLL;

namespace SampleApl
{
    public interface IWrrUsb2
    {
        long USB2_initialize();
        long USB2_uninitialize();
        long USB2_getModuleConnectionList(short[] list, ref ushort number);
        long USB2_open(long id);
        long USB2_close(long id);
        long USB2_getModuleInformation(long id, ref Usb2Struct.CModuleInformation information);
        long USB2_getSpectroInformation(long id, ref Usb2Struct.CSpectroInformation information);
        long USB2_getCalibrationCoefficient(long id, long index, double[] coefficient);
        long USB2_getLDPower(long id, ref long LDpower);
        long USB2_setLDPower(long id, long LDpower);
        long USB2_getLDPowerEnable(long id, ref long PowerEnable);
        long USB2_setLDPowerEnable(long id, long PowerEnable);
        long USB2_getLDTemp(long id, ref long LDTemp);
        long USB2_getLDBoardTemp(long id, ref long LDBoardTemp);
        long USB2_setCaptureMode(long id, long mode);
        long USB2_setTriggerMode(long id, long mode);
        long USB2_setDataCount(long id, long count);
        long USB2_setDataTransmit(long id, long transmit);
        long USB2_setExposureCycle(long id, double sec);
        long USB2_setExposureTime(long id, double sec);
        long USB2_setGain(long id, long mode, long gain);
        long USB2_getImageSize(long id, ref long sizeX, ref long sizeY);
        long USB2_allocateBuffer(long id, long frame);
        long USB2_captureStart(long id, long frame);
        long USB2_captureStop(long id);
        long USB2_getCaptureStatus(long id, ref long frame, ref long index);
        long USB2_getImageHeaderData(long id, ref ushort[] headerData, ref ushort[] imageData, long index, long frame, ref ulong[] time);
        long USB2_releaseBuffer(long id);
        long USB2_fireTrigger(long id);
    }
}
