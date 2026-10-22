import { API_BASE } from '../api/walklahApi'

const MAX_SIDE = 1280
const QUALITY = 0.8

/**
 * Shrinks a camera photo on the phone and re-encodes it as JPEG (about 150-300 KB).
 * Re-encoding through a canvas also drops EXIF data, including the GPS position.
 */
export async function preparePhoto(file: File): Promise<string> {
  if (!file.type.startsWith('image/')) throw new Error('Please choose a photo.')
  const bitmap = await loadBitmap(file)
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height))
  const width = Math.round(bitmap.width * scale)
  const height = Math.round(bitmap.height * scale)
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error("This browser can't prepare photos.")
  ctx.drawImage(bitmap, 0, 0, width, height)
  if ('close' in bitmap) bitmap.close()
  return canvas.toDataURL('image/jpeg', QUALITY)
}

async function loadBitmap(file: File): Promise<ImageBitmap | HTMLImageElement> {
  if ('createImageBitmap' in window) {
    try {
      // Respects the phone's rotation flag so portrait photos stay upright.
      return await createImageBitmap(file, { imageOrientation: 'from-image' })
    } catch {
      // Fall back to an <img> below (e.g. HEIC on some browsers).
    }
  }
  const url = URL.createObjectURL(file)
  try {
    const img = new Image()
    img.src = url
    await img.decode()
    return img
  } catch {
    throw new Error("That photo couldn't be read. Try JPEG or PNG.")
  } finally {
    URL.revokeObjectURL(url)
  }
}

/** Absolute URL for a report photo: an API path (e.g. /reports/report_3/photo) or a full storage link. */
export function photoSrc(path: string | null | undefined): string | null {
  if (!path) return null
  return /^https?:\/\//.test(path) ? path : `${API_BASE}${path}`
}
