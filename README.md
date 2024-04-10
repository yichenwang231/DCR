# Prototypical Classifier with Distribution Consistency Regularization for Generalized Category Discovery: A Strong Baseline

Generalized Category Discovery (GCD) generalizes semi-supervised learning to a more realistic and challenging  setting where unlabeled data contains samples from both known and novel categories. Recently, prototypical classifier has shown prominent performance on this issue, with the Softmax-based Cross-Entropy loss (SCE) commonly employed to optimize the distance between a sample and prototypes. However, the inherent non-bijectiveness of SCE prevents it from resolving intraclass relations among samples, resulting in semantic ambiguity. To mitigate this issue, we propose Distribution Consistency Regularization (DCR) for prototypical classifier. By leveraging a simple intraclass consistency loss, we enforce the classifier to yield similar outputs for samples belonging to the same class. In doing so, we equip classifier to better capture local structures and alleviate semantic ambiguity. Additionally, we propose using partial labels, rather than hard pseudo labels, to explore potential positive pairs in unlabeled data, thereby reducing the risk of introducing noisy supervisory signals. DCR requires no external sophisticated module, rendering the enhanced model concise and efficient. Extensive experiments validate consistent performance benefits of DCR while  achieving competitive or better performance on six benchmarks. Hence, our method can serve as a strong baseline for GCD.

## Running

### Dependencies

```
pip install -r requirements.txt
```

### Config

Set paths to datasets and desired log directories in ```config.py```


### Datasets

We use fine-grained benchmarks in this paper, including:

* [CUB-200-2011](http://www.vision.caltech.edu/visipedia-data/CUB-200-2011/CUB_200_2011.tgz)
* Stanford Cars ([Img](http://imagenet.stanford.edu/internal/car196/car_ims.tgz), [Annotation](http://imagenet.stanford.edu/internal/car196/cars_annos.mat))
- [FGVC-Aircraft](https://www.robots.ox.ac.uk/~vgg/data/fgvc-aircraft/)


We use oarse-grained benchmarks in this paper, including:

* [CIFAR-10/100](https://pytorch.org/vision/stable/datasets.html)
* [ImageNet-100](https://image-net.org/download.php)

### Scripts

**Train the model**:

```
bash scripts/run_${DATASET_NAME}.sh
```

## Acknowledgements

The code repo is largely built on this repo: https://github.com/sgvaze/generalized-category-discovery.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
