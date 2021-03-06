import numpy as np
import random
import math
from application import luna
from application.luna import LunaDataLoader

from interfaces.preprocess import BasePreprocessor
from utils.transformation_3d import affine_transform, apply_affine_transform
from interfaces.data_loader import INPUT, OUTPUT



DEFAULT_AUGMENTATION_PARAMETERS = {
    "scale": [1, 1, 1],  # factor
    "rotation": [0, 0, 0],  # degrees
    "shear": [0, 0, 0],  # degrees
    "translation": [0, 0, 0],  # mm
    "reflection": [0, 0, 0] #Bernoulli p
}


def log_uniform(max_val):
    return math.exp(uniform(math.log(max_val)))


def uniform(max_val):
    return max_val*(random.random()*2-1)


def bernoulli(p):
    return random.random() < p  #range [0.0, 1.0)


MAX_HU = 400.
MIN_HU = -1000.
PIXEL_MEAN = 0.25
NORMSCALE = 1./(MAX_HU - MIN_HU)
NORMOFFSET = - MIN_HU*NORMSCALE - PIXEL_MEAN
def normalize_and_center(x): return x*NORMSCALE + NORMOFFSET


# def lio_augment_positive_only(volume, pixel_spacing, output_shape, norm_patch_shape, augment_p,additional_translation, interp_order=1, cval=MIN_HU):

    
#     input_shape = np.asarray(volume.shape, np.float)
#     pixel_spacing = np.asarray(pixel_spacing, np.float)
#     output_shape = np.asarray(output_shape, np.float)
#     norm_patch_shape = np.asarray(norm_patch_shape, np.float)

#     norm_shape = input_shape * pixel_spacing
#     # this will stretch in some dimensions, but the stretch is consistent across samples
#     patch_shape = norm_shape * output_shape / norm_patch_shape
#     # else, use this: patch_shape = norm_shape * np.min(output_shape / norm_patch_shape)

#     shift_center = affine_transform(translation=-input_shape / 2. - 0.5)
#     normscale = affine_transform(scale=norm_shape / input_shape)
#     patch_centered = affine_transform(translation=additional_translation)
#     augment = affine_transform(**augment_p)
#     patchscale = affine_transform(scale=patch_shape / norm_shape)
#     unshift_center = affine_transform(translation=output_shape / 2. - 0.5)

#     matrix = shift_center.dot(normscale).dot(patch_centered).dot(augment).dot(patchscale).dot(unshift_center)

#     output = apply_affine_transform(volume, matrix,
#                                     order=interp_order,
#                                     output_shape=output_shape.astype("int"),
#                                     cval=cval)
#     return output



def lio_augment(volume, pixel_spacing, output_shape, norm_patch_shape, augment_p, interp_order=1,center_to_shift=None, cval=MIN_HU):


    if center_to_shift is None:
        #if no explicit center has been given, just center the image at the origin
        center_to_shift=-input_shape / 2. - 0.5
    
    
    input_shape = np.asarray(volume.shape, np.float)
    pixel_spacing = np.asarray(pixel_spacing, np.float)
    output_shape = np.asarray(output_shape, np.float)
    norm_patch_shape = np.asarray(norm_patch_shape, np.float)

    norm_shape = input_shape * pixel_spacing
    # this will stretch in some dimensions, but the stretch is consistent across samples
    patch_shape = norm_shape * output_shape / norm_patch_shape
    # else, use this: patch_shape = norm_shape * np.min(output_shape / norm_patch_shape)

    shift_center = affine_transform(translation=center_to_shift)
    normscale = affine_transform(scale=norm_shape / input_shape)
    augment = affine_transform(**augment_p)
    patchscale = affine_transform(scale=patch_shape / norm_shape)
    unshift_center = affine_transform(translation=output_shape / 2. - 0.5)

    matrix = shift_center.dot(normscale).dot(augment).dot(patchscale).dot(unshift_center)

    output = apply_affine_transform(volume, matrix,
                                    order=interp_order,
                                    output_shape=output_shape.astype("int"),
                                    cval=cval)
    return output


def sample_augmentation_parameters(augm_param):

    augm = dict(augm_param)
    
    augm["scale"] = [log_uniform(v) for v in augm_param["scale"]]
    augm["rotation"] = [uniform(v) for v in augm_param["rotation"]]
    augm["shear"] = [uniform(v) for v in augm_param["shear"]]
    augm["translation"] = [uniform(v) for v in augm_param["translation"]]
    augm["reflection"] = [bernoulli(v) for v in augm_param["reflection"]]
    
    return augm


class LioAugment(BasePreprocessor):
    def __init__(self, tags, output_shape, norm_patch_size, augmentation_params=DEFAULT_AUGMENTATION_PARAMETERS):
        """
        :param output_shape: the output shape in shape of the array
        :param norm_patch_size: the output shape in mm's
        :param augmentation_params: the parameters used for sampling the augmentation.
        :return:
        """
        self.augmentation_params = augmentation_params
        self.output_shape = output_shape
        self.norm_patch_size = norm_patch_size
        self.tags = tags

    @property
    def extra_input_tags_required(self):
        """
        We need some extra parameters to be loaded!
        :return:
        """
        datasetnames = set()
        for tag in self.tags:
            datasetnames.add(tag.split(':')[0])

        input_tags_extra = [dsn+":pixelspacing" for dsn in datasetnames]
        return input_tags_extra


    def process(self, sample):
        augment_p = sample_augmentation_parameters(self.augmentation_params)
        for tag in self.tags:
            pixelspacingtag = tag.split(':')[0]+":pixelspacing"
            assert pixelspacingtag in sample[INPUT], "tag %s not found"%pixelspacingtag
            spacing = sample[INPUT][pixelspacingtag]

            if tag in sample[INPUT]:
                volume = sample[INPUT][tag]
                sample[INPUT][tag] = lio_augment(
                    volume=volume,
                    pixel_spacing=spacing,
                    output_shape=self.output_shape,
                    norm_patch_shape=self.norm_patch_size,
                    augment_p=augment_p
                )
            elif tag in sample[OUTPUT]:
                volume = sample[OUTPUT][tag]
                sample[OUTPUT][tag] = lio_augment(
                    volume=volume,
                    pixel_spacing=spacing,
                    output_shape=self.output_shape,
                    norm_patch_shape=self.norm_patch_size,
                    augment_p=augment_p,
                    cval=0.0
                )
            else:
                pass
                #raise Exception("Did not find tag which I had to augment: %s"%tag)


class AugmentOnlyPositive(LioAugment):
    @property
    def extra_input_tags_required(self):
        """
        We need some extra parameters to be loaded!
        :return:
        """
        datasetnames = set()
        for tag in self.tags:
            datasetnames.add(tag.split(':')[0])

        input_tags_extra = [dsn+":pixelspacing" for dsn in datasetnames]
        input_tags_extra += [dsn+":labels" for dsn in datasetnames]
        input_tags_extra += [dsn+":origin" for dsn in datasetnames]
        return input_tags_extra


    def process(self, sample):
        orig_augment = sample_augmentation_parameters(self.augmentation_params)

        for tag in self.tags:

            pixelspacingtag = tag.split(':')[0]+":pixelspacing"
            labelstag = tag.split(':')[0]+":labels"
            origintag = tag.split(':')[0]+":origin"

            assert pixelspacingtag in sample[INPUT], "tag %s not found"%pixelspacingtag
            assert labelstag in sample[INPUT], "tag %s not found"%labelstag
            assert origintag in sample[INPUT], "tag %s not found"%origintag

            spacing = sample[INPUT][pixelspacingtag]
            labels = sample[INPUT][labelstag]
            origin = sample[INPUT][origintag]

            label = random.choice(labels)

            labelloc = LunaDataLoader.world_to_voxel_coordinates(label[:3],origin=origin, spacing=spacing)

            if tag in sample[INPUT]:
                volume = sample[INPUT][tag]

                augment_p = dict(orig_augment)
                #augment_p["translation"] = augment_p["translation"] + (0.5*np.array(volume.shape)-labelloc)*spacing

                sample[INPUT][tag] = lio_augment(
                    volume=volume,
                    pixel_spacing=spacing,
                    output_shape=self.output_shape,
                    norm_patch_shape=self.norm_patch_size,
                    augment_p=augment_p,
                    center_to_shift= - labelloc                     
                )
            elif tag in sample[OUTPUT]:
                volume = sample[OUTPUT][tag]

                augment_p = dict(orig_augment)
                #augment_p["translation"] = augment_p["translation"] + (0.5*np.array(volume.shape)-labelloc)*spacing

                
                
                sample[OUTPUT][tag] = lio_augment(
                    volume=volume,
                    pixel_spacing=spacing,
                    output_shape=self.output_shape,
                    norm_patch_shape=self.norm_patch_size,
                    augment_p=augment_p,
                    center_to_shift= - labelloc,                    
                    cval=0.0
                )
            else:
                pass
                #raise Exception("Did not find tag which I had to augment: %s"%tag)
