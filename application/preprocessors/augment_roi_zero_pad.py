import numpy as np
from glob import glob
import cPickle

from interfaces.data_loader import INPUT, OUTPUT
from augmentation_3d import sample_augmentation_parameters, Augment3D, augment_3d
from utils.paths import MODEL_PREDICTIONS_PATH

class AugmentROIZeroPad(Augment3D):
    """
    Generates zero padded roi augmented patches
    """

    def __init__(self, max_rois, roi_config, *args, **kwargs):
        super(AugmentROIZeroPad, self).__init__(*args, **kwargs)
        self.max_rois = max_rois
        if not isinstance(roi_config, str): roi_config = roi_config.__name__

        #load rois
        rootdir = MODEL_PREDICTIONS_PATH + roi_config
        rois = {}
        for path in glob(rootdir+"/*"):
            patient_id = path.split("/")[-1][:-4]
            with open(path, "rb") as f: rois[patient_id] = cPickle.load(f)

        self.rois = rois

    @property
    def extra_input_tags_required(self):
        input_tags_extra = super(AugmentROIZeroPad, self).extra_input_tags_required
        datasetnames = set()
        for tag in self.tags: datasetnames.add(tag.split(':')[0])
        input_tags_extra += [dsn + ":patient_id" for dsn in datasetnames]
        input_tags_extra += [dsn + ":3d" for dsn in datasetnames]
        return input_tags_extra

    def process(self, sample):
        augment_p = sample_augmentation_parameters(self.augmentation_params)

        for tag in self.tags:
            pixelspacingtag = tag.split(':')[0] + ":pixelspacing"
            assert pixelspacingtag in sample[INPUT], "tag %s not found" % pixelspacingtag
            spacing = sample[INPUT][pixelspacingtag]

            volume = sample[INPUT][tag]
            new_vol = np.zeros((self.max_rois,)+self.output_shape, volume.dtype)

            patient_id = sample[INPUT][tag.split(':')[0] + ":patient_id"]
            rois = self.rois[patient_id]
            np.random.shuffle(rois)

            for i in range(min(len(rois), self.max_rois)):
                # mm to input space
                center_to_shift = -rois[i]/np.asarray(spacing, np.float)
                # print rois[i], center_to_shift

                new_vol[i] = augment_3d(
                    volume=volume,
                    pixel_spacing=spacing,
                    output_shape=self.output_shape,
                    norm_patch_shape=self.norm_patch_shape,
                    augment_p=augment_p,
                    center_to_shift=center_to_shift
                )

            sample[INPUT][tag] = new_vol # shape: (max_rois, X, Y, Z)
