export const loadImage = (src: string): Promise<HTMLImageElement> => {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Failed to load image: ${src.substring(0, 100)}`));
    img.src = src;
  });
};

export const getImageDimensions = (img: HTMLImageElement) => {
  return {
    width: img.naturalWidth,
    height: img.naturalHeight,
  };
};

export const calculateScaledDimensions = (
  naturalWidth: number,
  naturalHeight: number,
  maxWidth: number,
  maxHeight: number
) => {
  const aspectRatio = naturalWidth / naturalHeight;

  let width = naturalWidth;
  let height = naturalHeight;

  if (width > maxWidth) {
    width = maxWidth;
    height = width / aspectRatio;
  }

  if (height > maxHeight) {
    height = maxHeight;
    width = height * aspectRatio;
  }

  return { width, height, scale: width / naturalWidth };
};

export const scaleCoordinates = (
  coords: { x: number; y: number },
  scale: number
): { x: number; y: number } => {
  return {
    x: coords.x * scale,
    y: coords.y * scale,
  };
};

export const unscaleCoordinates = (
  coords: { x: number; y: number },
  scale: number
): { x: number; y: number } => {
  return {
    x: Math.round(coords.x / scale),
    y: Math.round(coords.y / scale),
  };
};
