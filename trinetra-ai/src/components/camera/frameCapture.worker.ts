/** JPEG work stays off the video/UI thread; one reusable surface per player. */
const scope = self as unknown as {
  onmessage: ((event: MessageEvent<{ id: number; bitmap: ImageBitmap }>) => void) | null;
  postMessage: (message: { id: number; blob?: Blob; error?: string }) => void;
};
let canvas: OffscreenCanvas | null = null;
scope.onmessage = async ({ data: { id, bitmap } }) => {
  try {
    canvas ??= new OffscreenCanvas(bitmap.width, bitmap.height);
    if (canvas.width !== bitmap.width) canvas.width = bitmap.width;
    if (canvas.height !== bitmap.height) canvas.height = bitmap.height;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('Capture canvas unavailable');
    context.drawImage(bitmap, 0, 0);
    const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality: .9 });
    scope.postMessage({ id, blob });
  } catch {
    scope.postMessage({ id, error: 'Background frame encoding unavailable' });
  } finally {
    bitmap.close();
  }
};
export {};
