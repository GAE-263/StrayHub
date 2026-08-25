import liff from "@line/liff";

export function isLiffScannerAvailable(): boolean {
  try {
    return liff.isApiAvailable("scanCodeV2");
  } catch {
    return false;
  }
}

export async function scanAnimalQr(): Promise<string | null> {
  const result = await liff.scanCodeV2();
  return result.value;
}
