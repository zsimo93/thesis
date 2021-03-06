from PIL import Image, ImageFile
import fileModule
import io, time

def main(args):
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    fm = fileModule.FileManager()

    begin = time.time()
    data = fm.loadFile(args["id1"])
    image0 = Image.open(io.BytesIO(data.read()))
    elapsed = time.time() - begin
    print ("read Time " + repr(elapsed))

    begin = time.time()
    data = fm.loadFile(args["id2"])
    image1 = Image.open(io.BytesIO(data.read()))
    elapsed = time.time() - begin
    print ("read Time " + repr(elapsed))

    begin = time.time()
    data = fm.loadFile(args["id3"])
    image2 = Image.open(io.BytesIO(data.read()))
    elapsed = time.time() - begin
    print ("read Time " + repr(elapsed))

    begin = time.time()
    data = fm.loadFile(args["id4"])
    image3 = Image.open(io.BytesIO(data.read()))
    elapsed = time.time() - begin
    print ("read Time " + repr(elapsed))

    base_width, base_height = image0.size
    new_image = Image.new('RGB', (2 * base_width, 2 * base_height))

    new_image.paste(image0, (0, 0))
    new_image.paste(image1, (base_width, 0))
    new_image.paste(image2, (0, base_height))
    new_image.paste(image3, (base_width, base_height))

    newImage = io.BytesIO()
    new_image.save(newImage, 'PNG')
    newImage.seek(0)
    begin = time.time()
    retId = fm.saveFile(newImage, "image." + 'PNG')
    elapsed = time.time() - begin
    print ("write Time " + repr(elapsed))
    return {"retId": retId}
