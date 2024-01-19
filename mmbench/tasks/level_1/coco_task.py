import os
import json
from typing import Dict

from mmbench.common.registry import Registry
from mmbench.tasks.base_task import BaseTask
from collections import defaultdict

@Registry.register_task('COCO')
class COCOTask(BaseTask):
    def __init__(self, task_cfg, **kw_args):
        self.task_name = 'COCO'
        super().__init__(task_cfg, **kw_args)
        
    def calc_scores(self, args, results_df) -> Dict:
        metrics_scores = {}
        metric_cls = Registry.get_metric_class('caption')
        buffer_size = 4000 # The max length of string to pass into java
        # group results by image_id
        now = 0
        label_dict, pred_dict = {}, {}
        for image_id, sub_df in list(results_df.groupby(by="question_id")):
            label_dict[image_id] = [x.strip() for x in sub_df["answer"].unique().tolist()]
            pred_dict[image_id] = [x.strip() for x in sub_df["preds"].unique().tolist()]
            now += sum(map(len, label_dict[image_id])) + sum(map(len, pred_dict[image_id]))
            if now >= buffer_size:
                metrics_scores = metric_cls.calc_scores(pred_dict, label_dict)
                label_dict, pred_dict = {}, {}
        if not label_dict and not pred_dict:
            metrics_scores = metric_cls.calc_scores(pred_dict, label_dict)
        all_scores = defaultdict(float)
        for k in metrics_scores:
            for m in metrics_scores[k]:
                if m == 'SPICE':
                    all_scores[m] += metrics_scores[k][m]['ALL']
                else:
                    all_scores[m] += metrics_scores[k][m]
        for m in all_scores:
            all_scores[m] /= len(metrics_scores)
        return all_scores
